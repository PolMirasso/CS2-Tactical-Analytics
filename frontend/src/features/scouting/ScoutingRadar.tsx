import { useMemo, useRef, useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import type { Region, UtilityType, ZoneOut, ZoneUtilStat } from '@/types/api'

const VIEW = 1024
const MIN_BOX = 46

export const UTIL_COLOR: Record<UtilityType, string> = {
  smoke: '#9aa3b2',
  flash: '#f3c244',
  molotov: '#ff7a45',
  he: '#ff5d5d',
}
export const UTIL_GLYPH: Record<UtilityType, string> = {
  smoke: 'S',
  flash: 'F',
  molotov: 'M',
  he: 'H',
}
const REGION_COLOR: Record<string, string> = { A: '#4f8cff', B: '#ff5d5d', Mid: '#f3c244' }

export interface Token {
  id: string
  util_type: UtilityType
  region: Region
  time_from: number
  time_to: number
  x: number
  y: number
  w: number
  h: number
}

export interface DrawnRect {
  x: number
  y: number
  w: number
  h: number
}

interface Props {
  mapId: string
  zones?: ZoneOut[]
  tokens?: Token[]
  onRemoveToken?: (id: string) => void
  onDrawZone?: (rect: DrawnRect) => void
  drawColor?: string
  heatmap?: ZoneUtilStat[]
  size?: number
}

export function ScoutingRadar({
  mapId,
  zones = [],
  tokens = [],
  onRemoveToken,
  onDrawZone,
  drawColor = '#ff7a45',
  heatmap,
  size = 520,
}: Props) {
  const drawing = !!onDrawZone
  const [hovered, setHovered] = useState<string | null>(null)
  const [draft, setDraft] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const heat = useMemo(() => {
    const by = new Map<string, number>()
    let max = 0
    for (const h of heatmap ?? []) {
      by.set(h.zone, h.total)
      if (h.total > max) max = h.total
    }
    return { by, max: Math.max(1, max) }
  }, [heatmap])

  const toView = (e: React.MouseEvent): [number, number] => {
    const svg = svgRef.current
    if (!svg) return [0, 0]
    const r = svg.getBoundingClientRect()
    const clamp = (v: number) => Math.max(0, Math.min(VIEW, v))
    return [clamp(((e.clientX - r.left) / r.width) * VIEW), clamp(((e.clientY - r.top) / r.height) * VIEW)]
  }

  const onDown = (e: React.MouseEvent) => {
    if (!drawing) return
    const [x, y] = toView(e)
    setDraft({ x0: x, y0: y, x1: x, y1: y })
  }
  const onMove = (e: React.MouseEvent) => {
    if (!drawing || !draft) return
    const [x, y] = toView(e)
    setDraft((d) => (d ? { ...d, x1: x, y1: y } : d))
  }
  const finish = () => {
    if (!draft) return
    let w = Math.abs(draft.x1 - draft.x0)
    let h = Math.abs(draft.y1 - draft.y0)
    let cx: number
    let cy: number
    if (w < MIN_BOX || h < MIN_BOX) {
      w = Math.max(w, MIN_BOX)
      h = Math.max(h, MIN_BOX)
      cx = draft.x0
      cy = draft.y0
    } else {
      cx = (draft.x0 + draft.x1) / 2
      cy = (draft.y0 + draft.y1) / 2
    }
    setDraft(null)
    onDrawZone?.({ x: Math.round(cx), y: Math.round(cy), w: Math.round(w), h: Math.round(h) })
  }

  return (
    <div
      style={{
        position: 'relative',
        width: size,
        height: size,
        maxWidth: '100%',
        aspectRatio: '1 / 1',
        flexShrink: 0,
        background: '#11141a',
        border: '1px solid var(--border)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <img
        src={apiUrl(`/maps/${mapId}/radar.png`)}
        alt={mapId}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 0.85 }}
      />
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', cursor: drawing ? 'crosshair' : 'default' }}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={finish}
        onMouseLeave={finish}
      >
        {drawing && <rect x={0} y={0} width={VIEW} height={VIEW} fill="transparent" />}

        {!drawing &&
          zones.map((z) => {
            if (!z.polygon) return null
            const active = hovered === z.id
            const total = heat.by.get(z.id) ?? 0
            const isHeat = !!heatmap
            const color = isHeat ? '#ff7a45' : REGION_COLOR[z.region] ?? '#888'
            const fillOpacity = isHeat ? 0.08 + 0.55 * (total / heat.max) : active ? 0.4 : 0.14
            return (
              <polygon
                key={z.id}
                points={z.polygon.map((p) => p.join(',')).join(' ')}
                fill={color}
                fillOpacity={fillOpacity}
                stroke={color}
                strokeWidth={active ? 2.5 : 1.2}
                strokeLinejoin="round"
                onMouseEnter={() => setHovered(z.id)}
                onMouseLeave={() => setHovered((h) => (h === z.id ? null : h))}
              >
                <title>{heatmap ? `${z.name} · ${total}` : z.name}</title>
              </polygon>
            )
          })}

        {!drawing &&
          heatmap &&
          zones.map((z) => {
            const total = heat.by.get(z.id) ?? 0
            if (total === 0) return null
            return (
              <text
                key={`h${z.id}`}
                x={z.centroid[0]}
                y={z.centroid[1]}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={13}
                fontWeight={700}
                fill="#fff"
                stroke="#11141a"
                strokeWidth={3}
                paintOrder="stroke"
                style={{ pointerEvents: 'none' }}
              >
                {total}
              </text>
            )
          })}

        {draft && (
          <rect
            x={Math.min(draft.x0, draft.x1)}
            y={Math.min(draft.y0, draft.y1)}
            width={Math.abs(draft.x1 - draft.x0)}
            height={Math.abs(draft.y1 - draft.y0)}
            fill={drawColor}
            fillOpacity={0.18}
            stroke={drawColor}
            strokeWidth={2}
            strokeDasharray="6 4"
            style={{ pointerEvents: 'none' }}
          />
        )}

        {tokens.map((tk) => (
          <g
            key={tk.id}
            style={{ cursor: onRemoveToken ? 'pointer' : 'default' }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onRemoveToken?.(tk.id)}
          >
            <rect
              x={tk.x - tk.w / 2}
              y={tk.y - tk.h / 2}
              width={tk.w}
              height={tk.h}
              fill={UTIL_COLOR[tk.util_type]}
              fillOpacity={0.2}
              stroke={UTIL_COLOR[tk.util_type]}
              strokeWidth={2}
              rx={6}
            />
            <circle cx={tk.x} cy={tk.y} r={15} fill={UTIL_COLOR[tk.util_type]} stroke="#11141a" strokeWidth={2.5} />
            <text
              x={tk.x}
              y={tk.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={14}
              fontWeight={700}
              fill="#11141a"
              style={{ pointerEvents: 'none' }}
            >
              {UTIL_GLYPH[tk.util_type]}
            </text>
            <text
              x={tk.x}
              y={tk.y + tk.h / 2 + 14}
              textAnchor="middle"
              fontSize={13}
              fontWeight={600}
              fill="#fff"
              stroke="#11141a"
              strokeWidth={3}
              paintOrder="stroke"
              style={{ pointerEvents: 'none' }}
            >
              {tk.region} · {tk.time_from}–{tk.time_to}s
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

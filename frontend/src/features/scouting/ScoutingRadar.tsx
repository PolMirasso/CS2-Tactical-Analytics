import { useMemo, useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import type { Region, UtilityType, ZoneOut, ZoneUtilStat } from '@/types/api'

const VIEW = 1024

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
  zone: string
  region: Region
  round_time_s: number
  x: number
  y: number
}

interface Props {
  mapId: string
  zones: ZoneOut[]
  tokens?: Token[]
  onZoneClick?: (z: ZoneOut) => void
  onRemoveToken?: (id: string) => void
  heatmap?: ZoneUtilStat[]
  size?: number
}

export function ScoutingRadar({
  mapId,
  zones,
  tokens = [],
  onZoneClick,
  onRemoveToken,
  heatmap,
  size = 520,
}: Props) {
  const [hovered, setHovered] = useState<string | null>(null)

  const heat = useMemo(() => {
    const by = new Map<string, number>()
    let max = 0
    for (const h of heatmap ?? []) {
      by.set(h.zone, h.total)
      if (h.total > max) max = h.total
    }
    return { by, max: Math.max(1, max) }
  }, [heatmap])

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
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        {zones.map((z) => {
          if (!z.polygon) return null
          const active = hovered === z.id
          const total = heat.by.get(z.id) ?? 0
          const isHeat = !!heatmap
          const color = isHeat ? '#ff7a45' : REGION_COLOR[z.region] ?? '#888'
          const fillOpacity = isHeat
            ? 0.08 + 0.55 * (total / heat.max)
            : active
              ? 0.4
              : 0.14
          return (
            <polygon
              key={z.id}
              points={z.polygon.map((p) => p.join(',')).join(' ')}
              fill={color}
              fillOpacity={fillOpacity}
              stroke={color}
              strokeWidth={active ? 2.5 : 1.2}
              strokeLinejoin="round"
              style={{ cursor: onZoneClick ? 'pointer' : 'default' }}
              onMouseEnter={() => setHovered(z.id)}
              onMouseLeave={() => setHovered((h) => (h === z.id ? null : h))}
              onClick={() => onZoneClick?.(z)}
            >
              <title>{heatmap ? `${z.name} · ${total}` : z.name}</title>
            </polygon>
          )
        })}

        {/* Heatmap counts as labels on the busiest zones. */}
        {heatmap &&
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

        {/* Placed utility tokens (click to remove). */}
        {tokens.map((tk) => (
          <g
            key={tk.id}
            style={{ cursor: onRemoveToken ? 'pointer' : 'default' }}
            onClick={() => onRemoveToken?.(tk.id)}
          >
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
              y={tk.y + 26}
              textAnchor="middle"
              fontSize={13}
              fontWeight={600}
              fill="#fff"
              stroke="#11141a"
              strokeWidth={3}
              paintOrder="stroke"
              style={{ pointerEvents: 'none' }}
            >
              {tk.round_time_s}s
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

import { useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import type { MapCalibration, ZoneOut } from '@/types/api'

interface Props {
  zones: ZoneOut[]
  mapId: string
  hasRadar: boolean
  calibration: MapCalibration | null
  size?: number
}

const RADAR = 1024
const REGION_COLOR: Record<string, string> = {
  A: '#4f8cff',
  B: '#ff5d5d',
  Mid: '#f3c244',
}

export function ZoneScatter({ zones, mapId, hasRadar, calibration, size = 420 }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  if (zones.length === 0) return null

  let project: (x: number, y: number) => [number, number]
  if (hasRadar && calibration) {
    const cal = calibration
    project = (x, y) => [(x - cal.pos_x) / cal.scale, (cal.pos_y - y) / cal.scale]
  } else {
    const xs = zones.flatMap((z) => [z.bounds[0], z.bounds[2]])
    const ys = zones.flatMap((z) => [z.bounds[1], z.bounds[3]])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const pad = 60
    const span = Math.max(maxX - minX, maxY - minY) || 1
    project = (x, y) => [
      pad + ((x - minX) / span) * (RADAR - 2 * pad),
      pad + ((maxY - y) / span) * (RADAR - 2 * pad),
    ]
  }

  // Draw the hovered zone last so it sits on top of any it overlaps.
  const ordered = hovered ? [...zones.filter((z) => z.id !== hovered), zones.find((z) => z.id === hovered)!] : zones

  return (
    <div
      style={{
        position: 'relative',
        width: size,
        height: size,
        flexShrink: 0,
        background: '#11141a',
        border: '1px solid var(--border)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {hasRadar && (
        <img
          src={apiUrl(`/maps/${mapId}/radar.png`)}
          alt={mapId}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 0.9 }}
        />
      )}
      <svg viewBox={`0 0 ${RADAR} ${RADAR}`} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
        {ordered.map((z) => {
          const active = hovered === z.id
          const dim = hovered !== null && !active
          const color = REGION_COLOR[z.region] ?? '#888'
          const common = {
            fill: color,
            fillOpacity: active ? 0.55 : dim ? 0.08 : 0.22,
            stroke: color,
            strokeWidth: active ? 3.5 : 2,
            strokeLinejoin: 'round' as const,
            style: { cursor: 'pointer' as const },
            onMouseEnter: () => setHovered(z.id),
            onMouseLeave: () => setHovered((h) => (h === z.id ? null : h)),
          }
          if (z.polygon) {
            return (
              <polygon key={z.id} points={z.polygon.map((p) => project(p[0], p[1]).join(',')).join(' ')} {...common}>
                <title>{z.name}</title>
              </polygon>
            )
          }
          const [px0, py0] = project(z.bounds[0], z.bounds[3])
          const [px1, py1] = project(z.bounds[2], z.bounds[1])
          return (
            <rect key={z.id} x={px0} y={py0} width={px1 - px0} height={py1 - py0} rx={4} {...common}>
              <title>{z.name}</title>
            </rect>
          )
        })}
        {/* Labels on a top layer so text is never covered by another zone's fill. */}
        {ordered.map((z) => {
          const active = hovered === z.id
          const dim = hovered !== null && !active
          const [lx, ly] = project(z.centroid[0], z.centroid[1])
          return (
            <text
              key={z.id}
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={active ? 20 : 15}
              fontWeight={700}
              fill="#fff"
              fillOpacity={dim ? 0.3 : 1}
              stroke="#11141a"
              strokeWidth={active ? 4 : 3.5}
              paintOrder="stroke"
              style={{ pointerEvents: 'none' }}
            >
              {z.name}
            </text>
          )
        })}
      </svg>
    </div>
  )
}

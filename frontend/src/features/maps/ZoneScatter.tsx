import { useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import type { ZoneOut } from '@/types/api'

interface Props {
  zones: ZoneOut[]
  mapId: string
  size?: number
}

// Callout polygons live in the radar's 1024x1024 pixel space.
const VIEW = 1024
const REGION_COLOR: Record<string, string> = {
  A: '#4f8cff',
  B: '#ff5d5d',
  Mid: '#f3c244',
}

export function ZoneScatter({ zones, mapId, size = 460 }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  if (zones.length === 0) return null

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
      <img
        src={apiUrl(`/maps/${mapId}/radar.png`)}
        alt={mapId}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
      />
      <svg
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        {ordered.map((z) => {
          const active = hovered === z.id
          const dim = hovered !== null && !active
          const color = REGION_COLOR[z.region] ?? '#888'
          return (
            <polygon
              key={z.id}
              points={z.polygon ? z.polygon.map((p) => p.join(',')).join(' ') : ''}
              fill={color}
              fillOpacity={active ? 0.5 : dim ? 0.06 : 0.18}
              stroke={color}
              strokeWidth={active ? 3 : 1.5}
              strokeLinejoin="round"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHovered(z.id)}
              onMouseLeave={() => setHovered((h) => (h === z.id ? null : h))}
            >
              <title>{z.name}</title>
            </polygon>
          )
        })}
        {/* Labels on a top layer so text is never covered by another zone's fill. */}
        {ordered.map((z) => {
          const active = hovered === z.id
          const dim = hovered !== null && !active
          return (
            <text
              key={z.id}
              x={z.centroid[0]}
              y={z.centroid[1]}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={active ? 16 : 11}
              fontWeight={700}
              fill="#fff"
              fillOpacity={dim ? 0.25 : 1}
              stroke="#11141a"
              strokeWidth={active ? 3.5 : 2.5}
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

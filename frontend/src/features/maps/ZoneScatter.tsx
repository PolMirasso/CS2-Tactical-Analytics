import { useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import { REGION_COLOR } from '@/lib/colors'
import type { ZoneOut } from '@/types/api'

interface Props {
  zones: ZoneOut[]
  mapId: string
  size?: number
}

// Callout polygons live in the radar's 1024x1024 pixel space.
const VIEW = 1024

export function ZoneScatter({ zones, mapId, size = 460 }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  if (zones.length === 0) return null

  // Draw the hovered zone last so it sits on top of any it overlaps.
  const ordered = hovered ? [...zones.filter((z) => z.id !== hovered), zones.find((z) => z.id === hovered)!] : zones

  return (
    <div
      className="relative shrink-0 overflow-hidden rounded-lg border border-border bg-[#11141a]"
      style={{ width: size, height: size }}
    >
      <img
        src={apiUrl(`/maps/${mapId}/radar.png`)}
        alt={mapId}
        className="absolute inset-0 h-full w-full object-contain"
      />
      <svg
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
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
              className="cursor-pointer"
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
              className="pointer-events-none"
            >
              {z.name}
            </text>
          )
        })}
      </svg>
    </div>
  )
}

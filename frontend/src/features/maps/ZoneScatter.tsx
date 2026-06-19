import type { ZoneOut } from '@/types/api'

interface Props {
  zones: ZoneOut[]
  size?: number
}

const REGION_COLOR: Record<string, string> = {
  A: '#4f8cff',
  B: '#ff5d5d',
  Mid: '#f3c244',
}

// Quick SVG scatter of zone centroids in world space. A placeholder for the
// real tactical view (radar image + world→pixel transform per map).
export function ZoneScatter({ zones, size = 260 }: Props) {
  if (zones.length === 0) return null

  const xs = zones.map((z) => z.centroid[0])
  const ys = zones.map((z) => z.centroid[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const pad = 24
  const span = Math.max(maxX - minX, maxY - minY) || 1

  const project = (x: number, y: number): [number, number] => {
    const px = pad + ((x - minX) / span) * (size - 2 * pad)
    // Flip Y so the scatter is not upside down (screen Y grows downward).
    const py = pad + ((maxY - y) / span) * (size - 2 * pad)
    return [px, py]
  }

  return (
    <svg
      width={size}
      height={size}
      style={{ background: '#11141a', border: '1px solid var(--border)', borderRadius: 8 }}
    >
      {zones.map((z) => {
        const [px, py] = project(z.centroid[0], z.centroid[1])
        return (
          <g key={z.id}>
            <circle cx={px} cy={py} r={6} fill={REGION_COLOR[z.region] ?? '#888'} />
            <text x={px + 9} y={py + 4} fontSize={9} fill="#9aa3b2">
              {z.name}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

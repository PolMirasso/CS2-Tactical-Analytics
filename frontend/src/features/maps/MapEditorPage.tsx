import { useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '@/lib/apiClient'
import { REGION_COLOR } from '@/lib/colors'
import type { MapOut, Region, ZoneOut } from '@/types/api'
import { useMaps } from './hooks'

// Polygons are edited directly in the radar's 1024x1024 pixel space.
const VIEW = 1024
const REGIONS: Region[] = ['A', 'B', 'Mid']

type Pt = [number, number]
interface EditZone {
  id: string
  name: string
  region: Region
  polygon: Pt[]
}

type Drag =
  | { type: 'vertex'; zi: number; pi: number }
  | { type: 'move'; zi: number; last: Pt }
  | null

const round1 = (n: number) => Math.round(n * 10) / 10

function toEditZones(zones: ZoneOut[]): EditZone[] {
  return zones.map((z) => ({
    id: z.id,
    name: z.name,
    region: z.region,
    polygon: (z.polygon ?? []).map((p) => [p[0], p[1]] as Pt),
  }))
}

// Builds the exact JSON to paste into backend/app/assets/callouts/de_<map>.json
function exportJson(map: MapOut, zones: EditZone[]): string {
  return JSON.stringify({
    id: map.id,
    name: map.name,
    zones: zones.map((z) => ({
      id: z.id,
      name: z.name,
      region: z.region,
      polygon: z.polygon.map((p) => [round1(p[0]), round1(p[1])]),
    })),
  })
}

export function MapEditorPage() {
  const { data: maps, isLoading } = useMaps()
  const [mapId, setMapId] = useState<string | null>(null)
  const [zones, setZones] = useState<EditZone[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [drag, setDrag] = useState<Drag>(null)
  // Global recalibration: scale about the radar centre, then offset.
  const [scalePct, setScalePct] = useState(100)
  const [offX, setOffX] = useState(0)
  const [offY, setOffY] = useState(0)
  const [copied, setCopied] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)

  const map = useMemo(() => maps?.find((m) => m.id === mapId) ?? null, [maps, mapId])

  useEffect(() => {
    if (!mapId && maps && maps.length) setMapId(maps[0].id)
  }, [maps, mapId])

  useEffect(() => {
    if (map) {
      setZones(toEditZones(map.zones))
      setSelected(null)
      setScalePct(100)
      setOffX(0)
      setOffY(0)
    }
  }, [map])

  const svgPoint = (e: { clientX: number; clientY: number }): Pt => {
    const svg = svgRef.current
    if (!svg) return [0, 0]
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const m = svg.getScreenCTM()
    if (!m) return [0, 0]
    const p = pt.matrixTransform(m.inverse())
    return [p.x, p.y]
  }

  const updateZone = (zi: number, fn: (z: EditZone) => EditZone) =>
    setZones((zs) => zs.map((z, i) => (i === zi ? fn(z) : z)))

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag) return
    const [x, y] = svgPoint(e)
    if (drag.type === 'vertex') {
      updateZone(drag.zi, (z) => ({
        ...z,
        polygon: z.polygon.map((p, i) => (i === drag.pi ? [x, y] : p)),
      }))
    } else {
      const [lx, ly] = drag.last
      const dx = x - lx
      const dy = y - ly
      updateZone(drag.zi, (z) => ({ ...z, polygon: z.polygon.map(([px, py]) => [px + dx, py + dy]) }))
      setDrag({ ...drag, last: [x, y] })
    }
  }

  const endDrag = () => setDrag(null)

  // Insert a vertex on the nearest edge of the selected zone at the click point.
  const insertVertex = (e: React.MouseEvent) => {
    if (selected === null) return
    const [x, y] = svgPoint(e)
    updateZone(selected, (z) => {
      const poly = z.polygon
      let best = 0
      let bestD = Infinity
      for (let i = 0; i < poly.length; i++) {
        const a = poly[i]
        const b = poly[(i + 1) % poly.length]
        const d = pointSegDist([x, y], a, b)
        if (d < bestD) {
          bestD = d
          best = i
        }
      }
      const next = poly.slice()
      next.splice(best + 1, 0, [x, y])
      return { ...z, polygon: next }
    })
  }

  const deleteVertex = (zi: number, pi: number) =>
    updateZone(zi, (z) =>
      z.polygon.length > 3 ? { ...z, polygon: z.polygon.filter((_, i) => i !== pi) } : z,
    )

  const addZone = () => {
    if (!map) return
    const ids = new Set(zones.map((z) => z.id))
    let n = zones.length + 1
    while (ids.has(`${map.id}_zona_${n}`)) n++
    const c = VIEW / 2
    const zone: EditZone = {
      id: `${map.id}_zona_${n}`,
      name: `Nueva zona ${n}`,
      region: 'Mid',
      polygon: [
        [c - 60, c - 60],
        [c + 60, c - 60],
        [c + 60, c + 60],
        [c - 60, c + 60],
      ],
    }
    setZones((zs) => [...zs, zone])
    setSelected(zones.length)
  }

  const deleteZone = (zi: number) => {
    setZones((zs) => zs.filter((_, i) => i !== zi))
    setSelected(null)
  }

  const applyGlobal = () => {
    const s = scalePct / 100
    const cx = VIEW / 2
    const cy = VIEW / 2
    setZones((zs) =>
      zs.map((z) => ({
        ...z,
        polygon: z.polygon.map(([x, y]) => [cx + (x - cx) * s + offX, cy + (y - cy) * s + offY]),
      })),
    )
    setScalePct(100)
    setOffX(0)
    setOffY(0)
  }

  const json = map ? exportJson(map, zones) : ''
  const copy = async () => {
    await navigator.clipboard.writeText(json)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (isLoading) return <p className="text-muted">Loading…</p>

  return (
    <div>
      <h1>Editor de zonas</h1>
      <p className="text-muted">
        Arrastra los vértices para ajustar una zona. Click en una zona para seleccionarla; arrastra
        su interior para moverla entera. Doble-click en un borde añade un vértice; doble-click en un
        vértice lo borra. Usa la recalibración global para encajar todo el set sobre el radar.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={mapId ?? ''} onChange={(e) => setMapId(e.target.value)}>
          {maps?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <button className="border border-border bg-transparent text-text" onClick={() => map && setZones(toEditZones(map.zones))}>
          Restablecer
        </button>
        <button onClick={addZone} disabled={!map}>
          Agregar zona
        </button>
      </div>

      <div className="flex flex-wrap gap-6">
        <div className="relative h-[640px] w-[640px] shrink-0 overflow-hidden rounded-lg border border-border bg-[#11141a]">
          {map && (
            <img
              src={apiUrl(`/maps/${map.id}/radar.png`)}
              alt={map.id}
              className="absolute inset-0 h-full w-full object-contain"
            />
          )}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW} ${VIEW}`}
            className="absolute inset-0 h-full w-full touch-none"
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
          >
            {zones.map((z, zi) => {
              const active = selected === zi
              const color = REGION_COLOR[z.region] ?? '#888'
              return (
                <polygon
                  key={z.id}
                  points={z.polygon.map((p) => p.join(',')).join(' ')}
                  fill={color}
                  fillOpacity={active ? 0.45 : 0.16}
                  stroke={color}
                  strokeWidth={active ? 2.5 : 1.2}
                  strokeLinejoin="round"
                  className={active ? 'cursor-move' : 'cursor-pointer'}
                  onPointerDown={(e) => {
                    if (active) {
                      e.stopPropagation()
                      setDrag({ type: 'move', zi, last: svgPoint(e) })
                    } else {
                      setSelected(zi)
                    }
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation()
                    setSelected(zi)
                    insertVertex(e)
                  }}
                >
                  <title>{z.name}</title>
                </polygon>
              )
            })}
            {selected !== null &&
              zones[selected]?.polygon.map((p, pi) => (
                <circle
                  key={pi}
                  cx={p[0]}
                  cy={p[1]}
                  r={6}
                  fill="#fff"
                  stroke="#11141a"
                  strokeWidth={2}
                  className="cursor-grab"
                  onPointerDown={(e) => {
                    e.stopPropagation()
                    setDrag({ type: 'vertex', zi: selected, pi })
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation()
                    deleteVertex(selected, pi)
                  }}
                />
              ))}
          </svg>
        </div>

        <div className="flex min-w-[280px] flex-1 flex-col gap-4">
          <div className="m-0 rounded-[10px] border border-border bg-surface p-4 print:break-inside-avoid">
            <h3 className="mt-0">Recalibración global</h3>
            <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
              <span className="text-muted">Escala %</span>
              <input type="range" min={50} max={150} step={0.5} value={scalePct} onChange={(e) => setScalePct(+e.target.value)} />
              <input type="number" step={0.5} value={scalePct} onChange={(e) => setScalePct(+e.target.value)} className="w-[70px]" />
              <span className="text-muted">Offset X</span>
              <input type="range" min={-200} max={200} value={offX} onChange={(e) => setOffX(+e.target.value)} />
              <input type="number" value={offX} onChange={(e) => setOffX(+e.target.value)} className="w-[70px]" />
              <span className="text-muted">Offset Y</span>
              <input type="range" min={-200} max={200} value={offY} onChange={(e) => setOffY(+e.target.value)} />
              <input type="number" value={offY} onChange={(e) => setOffY(+e.target.value)} className="w-[70px]" />
            </div>
            <button className="mt-2.5" onClick={applyGlobal}>
              Aplicar a todas las zonas
            </button>
          </div>

          {selected !== null && zones[selected] && (
            <div className="m-0 rounded-[10px] border border-border bg-surface p-4 print:break-inside-avoid">
              <h3 className="mt-0">Zona seleccionada</h3>
              <label className="mb-2 block">
                Nombre
                <input
                  value={zones[selected].name}
                  onChange={(e) => updateZone(selected, (z) => ({ ...z, name: e.target.value }))}
                  className="w-full"
                />
              </label>
              <label className="block">
                Región
                <select
                  value={zones[selected].region}
                  onChange={(e) => updateZone(selected, (z) => ({ ...z, region: e.target.value as Region }))}
                  className="w-full"
                >
                  {REGIONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <p className="mb-2 text-muted">
                {zones[selected].polygon.length} vértices · id <code>{zones[selected].id}</code>
              </p>
              <button
                onClick={() => deleteZone(selected)}
                className="border-danger bg-danger text-white"
              >
                Eliminar zona
              </button>
            </div>
          )}

          <div className="m-0 rounded-[10px] border border-border bg-surface p-4 print:break-inside-avoid">
            <h3 className="mt-0">Exportar</h3>
            <button onClick={copy}>{copied ? '¡Copiado!' : 'Copiar JSON'}</button>
            <textarea
              readOnly
              value={json}
              onFocus={(e) => e.target.select()}
              className="mt-2 h-[140px] w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-mono text-[11px] text-text"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function pointSegDist(p: Pt, a: Pt, b: Pt): number {
  const [px, py] = p
  const [ax, ay] = a
  const [bx, by] = b
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy || 1
  let t = ((px - ax) * dx + (py - ay) * dy) / len2
  t = Math.max(0, Math.min(1, t))
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(px - cx, py - cy)
}

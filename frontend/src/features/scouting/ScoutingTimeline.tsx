import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { UtilityType } from '@/types/api'
import { UTIL_COLOR } from '@/lib/colors'
import { UTIL_GLYPH, type Token } from './ScoutingRadar'
import { fmtClock, ROUND_TIME_S } from './clock'

const clamp = (v: number) => Math.max(0, Math.min(ROUND_TIME_S, v))
const pctOf = (s: number) => (clamp(s) / ROUND_TIME_S) * 100

type Edge = 'move' | 'from' | 'to'
type Drag = { kind: 'active' | 'token'; id?: string; edge: Edge; grab: number; from: number; to: number }

// greedy lane packing so overlapping windows stack on separate rows
function assignLanes(items: { from: number; to: number }[]): { lanes: number[]; count: number } {
  const order = items.map((it, i) => ({ it, i })).sort((a, b) => a.it.from - b.it.from)
  const laneEnd: number[] = []
  const lanes = new Array<number>(items.length).fill(0)
  for (const { it, i } of order) {
    let l = 0
    for (; l < laneEnd.length; l++) if (it.from >= laneEnd[l]) break
    lanes[i] = l
    laneEnd[l] = it.to
  }
  return { lanes, count: Math.max(1, laneEnd.length) }
}

// Round-clock ticks: 1:55 to 0:00
const TICKS = [115, 90, 60, 30, 0].map((clock) => ROUND_TIME_S - clock)

export function ScoutingTimeline({
  tokens,
  activeUtil,
  activeFrom,
  activeTo,
  drawColor,
  onActive,
  onToken,
}: {
  tokens: Token[]
  activeUtil: UtilityType
  activeFrom: number
  activeTo: number
  drawColor: string
  onActive: (from: number, to: number) => void
  onToken: (id: string, from: number, to: number) => void
}) {
  const { t } = useTranslation()
  const barRef = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<Drag | null>(null)

  const secAt = (clientX: number) => {
    const el = barRef.current
    if (!el) return 0
    const r = el.getBoundingClientRect()
    return clamp(((clientX - r.left) / r.width) * ROUND_TIME_S)
  }

  const commit = (d: Drag, from: number, to: number) => {
    const f = Math.round(from)
    const tt = Math.round(to)
    if (d.kind === 'active') onActive(f, tt)
    else onToken(d.id!, f, tt)
  }

  const onDown = (e: React.PointerEvent, base: Omit<Drag, 'grab'>) => {
    e.stopPropagation()
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ ...base, grab: secAt(e.clientX) })
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag) return
    const cur = secAt(e.clientX)
    if (drag.edge === 'from') {
      commit(drag, Math.min(cur, drag.to), drag.to)
    } else if (drag.edge === 'to') {
      commit(drag, drag.from, Math.max(cur, drag.from))
    } else {
      const dur = drag.to - drag.from
      let from = clamp(drag.from + (cur - drag.grab))
      from = Math.min(from, ROUND_TIME_S - dur)
      commit(drag, from, from + dur)
    }
  }
  const onUp = () => setDrag(null)

  const { lanes, count } = assignLanes(tokens.map((tk) => ({ from: tk.time_from, to: tk.time_to })))
  const LANE_H = 26
  const tokenAreaH = count * LANE_H

  // A draggable window segment (active "next" window or a placed token)
  const renderSegment = ({
    key,
    from,
    to,
    top,
    color,
    glyph,
    label,
    dashed,
    base,
  }: {
    key?: string
    from: number
    to: number
    top: number
    color: string
    glyph: string
    label: string
    dashed?: boolean
    base: { kind: 'active' | 'token'; id?: string }
  }) => {
    const left = pctOf(from)
    const width = pctOf(to) - left
    const gripColor = dashed ? color : 'rgba(0,0,0,0.55)'
    // A visible resize grip pinned to one edge (drag to grow/shrink the window).
    const Handle = (edge: Edge) => (
      <div
        onPointerDown={(e) => onDown(e, { ...base, edge, from, to })}
        onPointerMove={onMove}
        onPointerUp={onUp}
        className="absolute top-0 bottom-0 flex w-3 touch-none cursor-ew-resize items-center justify-center"
        style={{ [edge === 'from' ? 'left' : 'right']: 0 }}
      >
        <span
          className="h-[60%] w-[3px] rounded-[2px]"
          style={{ background: gripColor, boxShadow: `3px 0 0 -1px ${gripColor}` }}
        />
      </div>
    )
    return (
      <div
        key={key}
        title={`${label} · ${fmtClock(from)}–${fmtClock(to)}`}
        onPointerDown={(e) => onDown(e, { ...base, edge: 'move', from, to })}
        onPointerMove={onMove}
        onPointerUp={onUp}
        className={`absolute box-border flex min-w-[30px] touch-none cursor-grab items-center justify-center gap-1 overflow-hidden rounded-[5px] px-3 text-[11px] font-bold whitespace-nowrap select-none ${
          dashed ? 'border-[1.5px] border-dashed bg-white/4' : 'border border-black/35 text-[#11141a]'
        }`}
        style={{
          top,
          height: LANE_H - 6,
          left: `${left}%`,
          width: `${width}%`,
          // Colour is per-utility, so it stays inline: background doubles as the
          // border/text colour when the segment is dashed.
          background: dashed ? undefined : color,
          borderColor: dashed ? color : undefined,
          color: dashed ? color : undefined,
        }}
      >
        <span className="pointer-events-none">
          {glyph}
          {width > 9 && <span className="ml-1 font-medium opacity-85">{`${fmtClock(from)}–${fmtClock(to)}`}</span>}
        </span>
        {Handle('from')}
        {Handle('to')}
      </div>
    )
  }

  return (
    <div className={drag ? 'select-none' : undefined}>
      <div
        ref={barRef}
        className="relative touch-none rounded-md border border-border bg-[#11141a] pt-1.5"
      >
        {/* Clock axis */}
        <div className="relative mb-0.5 h-4">
          {TICKS.map((s, i) => (
            <span
              key={s}
              className="pointer-events-none absolute top-0 text-[11px] text-muted tabular-nums"
              style={{
                left: `${pctOf(s)}%`,
                transform: i === 0 ? 'none' : i === TICKS.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
              }}
            >
              {fmtClock(s)}
            </span>
          ))}
        </div>

        {/* Active ("next utility") lane */}
        <div className="relative" style={{ height: LANE_H }}>
          {TICKS.map((s) => (
            <div key={s} className="absolute top-0 bottom-0 w-px bg-border" style={{ left: `${pctOf(s)}%` }} />
          ))}
          {renderSegment({
            from: activeFrom,
            to: activeTo,
            top: 3,
            color: drawColor,
            glyph: UTIL_GLYPH[activeUtil],
            label: t(`scouting.utilTypes.${activeUtil}`),
            dashed: true,
            base: { kind: 'active' },
          })}
        </div>

        {/* Placed-utility lanes */}
        <div className="relative border-t border-border" style={{ height: tokenAreaH }}>
          {TICKS.map((s) => (
            <div key={s} className="absolute top-0 bottom-0 w-px bg-border" style={{ left: `${pctOf(s)}%` }} />
          ))}
          {tokens.map((tk, i) =>
            renderSegment({
              key: tk.id,
              from: tk.time_from,
              to: tk.time_to,
              top: lanes[i] * LANE_H + 3,
              color: UTIL_COLOR[tk.util_type],
              glyph: UTIL_GLYPH[tk.util_type],
              label: t(`scouting.utilTypes.${tk.util_type}`),
              base: { kind: 'token', id: tk.id },
            }),
          )}
        </div>
      </div>
      <p className="mt-1.5 mb-0 text-xs text-muted">
        {t('scouting.timelineHint')}
      </p>
    </div>
  )
}

interface Props {
  id: string
  min: number
  max: number
  step?: number
  value: [number, number]
  onChange: (value: [number, number]) => void
  minLabel: string
  maxLabel: string
  format?: (v: number) => string
}

const THUMB = 16

const THUMB_CLS = [
  '[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none',
  '[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full',
  '[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-bg [&::-webkit-slider-thumb]:bg-accent',
  '[&::-webkit-slider-thumb]:cursor-ew-resize',
  '[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:appearance-none',
  '[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full',
  '[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-bg [&::-moz-range-thumb]:bg-accent',
  '[&::-moz-range-thumb]:cursor-ew-resize',
  '[&:focus-visible::-webkit-slider-thumb]:outline-2 [&:focus-visible::-webkit-slider-thumb]:outline-offset-2',
  '[&:focus-visible::-webkit-slider-thumb]:outline-text',
  '[&:focus-visible::-moz-range-thumb]:outline-2 [&:focus-visible::-moz-range-thumb]:outline-offset-2',
  '[&:focus-visible::-moz-range-thumb]:outline-text',
].join(' ')

// Two stacked native ranges
export function RangeSlider({
  id, min, max, step = 1, value, onChange, minLabel, maxLabel, format,
}: Props) {
  const [low, high] = value
  const pctOf = (v: number) => (max > min ? ((v - min) / (max - min)) * 100 : 0)
  // Native thumbs are inset by half their width
  const posOf = (v: number) => `calc(${pctOf(v)}% + ${(0.5 - pctOf(v) / 100) * THUMB}px)`
  const spanPct = pctOf(high) - pctOf(low)

  const rangeCls = `pointer-events-none absolute inset-x-0 top-0 m-0 h-4 w-full appearance-none rounded-none border-0 bg-transparent p-0 focus-visible:outline-none ${THUMB_CLS}`

  return (
    <div className="relative h-4">
      <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full border border-border bg-surface-2" />
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent"
        style={{ left: posOf(low), width: `calc(${spanPct}% - ${(spanPct / 100) * THUMB}px)` }}
      />
      <input
        id={`${id}-min`}
        type="range"
        min={min}
        max={max}
        step={step}
        value={low}
        aria-label={minLabel}
        aria-valuetext={format?.(low)}
        onChange={(e) => onChange([Math.min(Number(e.target.value), high), high])}
        className={`${rangeCls} ${low > (min + max) / 2 ? 'z-20' : 'z-10'}`}
      />
      <input
        id={`${id}-max`}
        type="range"
        min={min}
        max={max}
        step={step}
        value={high}
        aria-label={maxLabel}
        aria-valuetext={format?.(high)}
        onChange={(e) => onChange([low, Math.max(Number(e.target.value), low)])}
        className={`${rangeCls} z-10`}
      />
    </div>
  )
}

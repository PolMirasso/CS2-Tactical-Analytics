interface Props {
  status: string
}

// Maps backend status strings (parsed/failed/running/…) to a coloured pill.
// Whole utility strings, never interpolated fragments — Tailwind only emits
// classes it can find literally in the source.
const TONE: Record<string, string> = {
  parsed: 'border-ok text-ok',
  completed: 'border-ok text-ok',
  failed: 'border-danger text-danger',
  cancelled: 'border-danger text-danger',
  running: 'border-warn text-warn',
  reparsing: 'border-warn text-warn',
  cancelling: 'border-warn text-warn',
  paused: 'border-warn text-warn',
  pending: 'border-warn text-warn',
}

export function StatusBadge({ status }: Props) {
  const tone = TONE[status] ?? ''
  return (
    <span
      className={`inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs ${tone}`}
    >
      {status}
    </span>
  )
}

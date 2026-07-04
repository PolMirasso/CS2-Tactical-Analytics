interface Props {
  status: string
}

// Maps backend status strings (parsed/failed/running/…) to a coloured pill.
const TONE: Record<string, string> = {
  parsed: 'ok',
  completed: 'ok',
  failed: 'failed',
  cancelled: 'failed',
  running: 'running',
  reparsing: 'running',
  cancelling: 'running',
  paused: 'pending',
  pending: 'pending',
}

export function StatusBadge({ status }: Props) {
  const tone = TONE[status] ?? ''
  return <span className={`badge ${tone}`}>{status}</span>
}

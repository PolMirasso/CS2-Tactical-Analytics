import i18n from '@/i18n'

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/

function toDate(iso: string): Date {
  const m = DATE_ONLY.exec(iso)
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(iso)
}

function locale(): string | undefined {
  return i18n.language?.startsWith('es') ? 'es-ES' : undefined
}

const DAY_PARTS = { day: '2-digit', month: '2-digit', year: 'numeric' } as const

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = toDate(iso)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleString(locale(), { ...DAY_PARTS, hour: '2-digit', minute: '2-digit' })
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = toDate(iso)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleDateString(locale(), DAY_PARTS)
}

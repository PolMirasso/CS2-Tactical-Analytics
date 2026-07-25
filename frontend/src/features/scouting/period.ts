import type { DateWindowParams } from '@/types/api'

export type PeriodPreset = 'all' | 'last_month' | 'last_3_months' | 'custom'

export const PERIOD_PRESETS: PeriodPreset[] = ['all', 'last_month', 'last_3_months', 'custom']

export type DateWindow = DateWindowParams

const PRESET_MONTHS: Partial<Record<PeriodPreset, number>> = {
  last_month: 1,
  last_3_months: 3,
}

const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// Calendar months back, clamped to the shorter month (31 Mar − 1 month = 28/29 Feb).
function monthsBack(n: number, today: Date): Date {
  const d = new Date(today.getFullYear(), today.getMonth() - n, 1)
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
  d.setDate(Math.min(today.getDate(), lastDay))
  return d
}

export function periodWindow(
  preset: PeriodPreset,
  customFrom = '',
  customTo = '',
  today: Date = new Date(),
): DateWindow {
  if (preset === 'custom') {
    // Either bound alone is a valid open-ended window.
    const [from, to] = customFrom && customTo && customFrom > customTo
      ? [customTo, customFrom]
      : [customFrom, customTo]
    return { date_from: from || undefined, date_to: to || undefined }
  }
  const months = PRESET_MONTHS[preset]
  if (!months) return {}
  return { date_from: isoDay(monthsBack(months, today)), date_to: isoDay(today) }
}

export function windowLabel(w: DateWindow): string {
  if (!w.date_from && !w.date_to) return ''
  return `${w.date_from ?? '…'} → ${w.date_to ?? '…'}`
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { RosterLineup, TeamRostersOut } from '@/types/api'

export function RosterChangeWarning({
  roster,
  selected,
  onSelect,
}: {
  roster: TeamRostersOut
  selected?: string
  onSelect?: (id: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const changes = roster.entries.filter((e) => e.added.length || e.removed.length)
  const pickable = !!onSelect && roster.lineups.length > 1

  return (
    <div className="mb-5 rounded-lg border border-l-4 border-warn bg-warn/8 px-3.5 py-3 text-[0.9rem]">
      <p className="mt-0 mb-1.5 font-semibold text-warn">⚠ {t('analytics.roster.title')}</p>
      <div>{t('analytics.roster.body', { count: changes.length })}</div>
      {roster.core.length > 0 && (
        <div className="mt-1.5 text-muted">
          {t('analytics.roster.core')}: {roster.core.join(', ')}
        </div>
      )}
      {pickable && (
        <div className="mt-2.5">
          <label htmlFor="sc-lineup" className="mb-1 text-[0.85rem]">
            {t('analytics.roster.filterLabel')}
          </label>
          <select
            id="sc-lineup"
            className="!mb-0 max-w-[520px]"
            value={selected ?? ''}
            onChange={(e) => onSelect?.(e.target.value)}
          >
            <option value="">{t('analytics.roster.allLineups')}</option>
            {roster.lineups.map((l) => (
              <option key={l.id} value={l.id}>{lineupLabel(l, roster.core)}</option>
            ))}
          </select>
          <p className="mt-1 mb-0 text-xs text-muted">
            {selected
              ? t('analytics.roster.scopedHint')
              : t('analytics.roster.pickHint')}
          </p>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-2 w-auto px-2 py-0.5 text-[0.8rem]"
      >
        {open ? t('analytics.roster.hide') : t('analytics.roster.details')}
      </button>
      {open && (
        <ul className="mt-2 mb-0 list-disc pl-[18px]">
          {changes.map((e) => (
            <li key={e.demo_id} className="my-0.5">
              {e.match_date && <span className="text-muted">{e.match_date} · </span>}
              {e.opponent && <span className="text-muted">vs {e.opponent} · </span>}
              {e.added.length > 0 && <span className="text-ok">+ {e.added.join(', ')}</span>}
              {e.added.length > 0 && e.removed.length > 0 && ' '}
              {e.removed.length > 0 && <span className="text-danger">− {e.removed.join(', ')}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function lineupLabel(l: RosterLineup, core: string[]): string {
  const diff = l.players.filter((p) => !core.includes(p))
  const span = l.first_date && l.last_date && l.first_date !== l.last_date
    ? `${l.first_date} → ${l.last_date}`
    : l.first_date ?? l.last_date ?? ''
  return [span, (diff.length ? diff : l.players).join(', '), `(${l.n_demos})`]
    .filter(Boolean)
    .join(' · ')
}

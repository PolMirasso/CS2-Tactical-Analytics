import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TeamRostersOut } from '@/types/api'

export function RosterChangeWarning({ roster }: { roster: TeamRostersOut }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const changes = roster.entries.filter((e) => e.added.length || e.removed.length)

  return (
    <div className="mb-5 rounded-lg border border-l-4 border-warn bg-warn/8 px-3.5 py-3 text-[0.9rem]">
      <p className="mt-0 mb-1.5 font-semibold text-warn">⚠ {t('analytics.roster.title')}</p>
      <div>{t('analytics.roster.body', { count: changes.length })}</div>
      {roster.core.length > 0 && (
        <div className="mt-1.5 text-muted">
          {t('analytics.roster.core')}: {roster.core.join(', ')}
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

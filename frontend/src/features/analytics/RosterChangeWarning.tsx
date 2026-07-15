import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TeamRostersOut } from '@/types/api'

export function RosterChangeWarning({ roster }: { roster: TeamRostersOut }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const changes = roster.entries.filter((e) => e.added.length || e.removed.length)

  return (
    <div className="warn-banner">
      <p className="warn-title">⚠ {t('analytics.roster.title')}</p>
      <div>{t('analytics.roster.body', { count: changes.length })}</div>
      {roster.core.length > 0 && (
        <div className="muted" style={{ marginTop: 6 }}>
          {t('analytics.roster.core')}: {roster.core.join(', ')}
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{ width: 'auto', marginTop: 8, padding: '2px 8px', fontSize: '0.8rem' }}
      >
        {open ? t('analytics.roster.hide') : t('analytics.roster.details')}
      </button>
      {open && (
        <ul>
          {changes.map((e) => (
            <li key={e.demo_id}>
              {e.match_date && <span className="muted">{e.match_date} · </span>}
              {e.opponent && <span className="muted">vs {e.opponent} · </span>}
              {e.added.length > 0 && <span className="in">+ {e.added.join(', ')}</span>}
              {e.added.length > 0 && e.removed.length > 0 && ' '}
              {e.removed.length > 0 && <span className="out">− {e.removed.join(', ')}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

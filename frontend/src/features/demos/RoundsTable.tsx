import { useTranslation } from 'react-i18next'
import type { RoundOut, Site, UtilityType } from '@/types/api'

const UTIL_COLOR: Record<UtilityType, string> = {
  smoke: '#9aa3b2',
  flash: '#f3c244',
  molotov: '#ff7a45',
  he: '#ff5d5d',
}

const SITES: Site[] = ['A', 'B', 'Mid', 'NoPlant']

function UtilityChips({ round }: { round: RoundOut }) {
  const { t } = useTranslation()
  if (round.utility.length === 0) return <span className="muted">{t('demos.noUtility')}</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {round.utility.map((u) => (
        <span
          key={u.id}
          className="badge"
          title={`${u.util_type} / ${u.zone ?? u.region ?? '-'} / ${u.round_time_s.toFixed(1)}s / ${u.team ?? ''}`}
          style={{ borderColor: UTIL_COLOR[u.util_type], color: UTIL_COLOR[u.util_type] }}
        >
          {u.util_type} / {u.zone ?? u.region ?? '-'} / {u.round_time_s.toFixed(0)}s
        </span>
      ))}
    </div>
  )
}

export function RoundsTable({ rounds }: { rounds: RoundOut[] }) {
  const { t } = useTranslation()

  const siteCounts = SITES.map(
    (s) => [s, rounds.filter((r) => r.target_site === s).length] as const,
  )
  const totalUtility = rounds.reduce((acc, r) => acc + r.utility.length, 0)

  if (rounds.length === 0) {
    return (
      <div className="card">
        <p className="muted">{t('demos.noRounds')}</p>
      </div>
    )
  }

  return (
    <>
      <div className="card">
        <h2>{t('demos.summary')}</h2>
        <p className="muted">
          {t('demos.siteDistribution')}:{' '}
          {siteCounts.map(([s, n]) => (
            <span key={s} className="badge" style={{ marginRight: 6 }}>
              {s}: {n}
            </span>
          ))}
        </p>
        <p className="muted">
          {t('demos.totalUtility')}: <strong>{totalUtility}</strong>
          <span style={{ marginLeft: 16 }}>
            {t('demos.rounds')}: <strong>{rounds.length}</strong>
          </span>
        </p>
      </div>

      <div className="card">
        <h2>{t('demos.rounds')}</h2>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{t('demos.buy')}</th>
              <th>{t('demos.site')}</th>
              <th>{t('demos.utility')}</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((r) => (
              <tr key={r.id}>
                <td>{r.round_number}</td>
                <td>
                  <span className="badge">{r.buy_type}</span>
                </td>
                <td>
                  <span className="badge">{r.target_site}</span>
                </td>
                <td>
                  <UtilityChips round={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

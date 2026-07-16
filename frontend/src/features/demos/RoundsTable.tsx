import { useTranslation } from 'react-i18next'
import { UTIL_COLOR } from '@/lib/colors'
import type { RoundOut, Site } from '@/types/api'

const SITES: Site[] = ['A', 'B', 'Mid', 'NoPlant']

const BUY_COLOR: Record<string, string> = {
  pistol: '#6fb1ff',
  full_eco: '#6b7280',
  eco: '#9aa3b2',
  ak_hero: '#ff7a45',
  m4_hero: '#4f8cff',
  awp_hero: '#c678dd',
  force: '#f3c244',
  full: '#7bd88f',
}

const money = (n: number) => `$${n.toLocaleString('en-US')}`

function UtilityChips({ round }: { round: RoundOut }) {
  const { t } = useTranslation()
  if (round.utility.length === 0) return <span className="text-muted">{t('demos.noUtility')}</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {round.utility.map((u) => (
        <span
          key={u.id}
          className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs"
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
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <p className="text-muted">{t('demos.noRounds')}</p>
      </div>
    )
  }

  return (
    <>
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('demos.summary')}</h2>
        <p className="text-muted">
          {t('demos.siteDistribution')}:{' '}
          {siteCounts.map(([s, n]) => (
            <span key={s} className="mr-1.5 inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">
              {s}: {n}
            </span>
          ))}
        </p>
        <p className="text-muted">
          {t('demos.totalUtility')}: <strong>{totalUtility}</strong>
          <span className="ml-4">
            {t('demos.rounds')}: <strong>{rounds.length}</strong>
          </span>
        </p>
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('demos.rounds')}</h2>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{t('demos.result', 'Resultado')}</th>
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
                  {r.winner ? (
                    <span
                      className={`inline-block rounded-full border bg-surface-2 px-2 py-0.5 text-xs ${
                        r.winner === 't' ? 'border-[#7bd88f] text-[#7bd88f]' : 'border-danger text-danger'
                      }`}
                      title={r.win_reason ?? ''}
                    >
                      {r.winner === 't' ? t('demos.won', 'Ganada') : t('demos.lost', 'Perdida')}
                    </span>
                  ) : (
                    <span className="text-muted">-</span>
                  )}
                </td>
                <td>
                  <span className="inline-flex items-center gap-2">
                    <span
                      className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs"
                      style={{ borderColor: BUY_COLOR[r.buy_type], color: BUY_COLOR[r.buy_type] }}
                    >
                      {t(`demos.buyTypes.${r.buy_type}`, r.buy_type)}
                    </span>
                    <span className="text-muted">{money(r.equip_value)}</span>
                  </span>
                </td>
                <td>
                  <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{r.target_site}</span>
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

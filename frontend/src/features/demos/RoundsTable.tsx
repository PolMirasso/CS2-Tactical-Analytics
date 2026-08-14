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
        <p className="my-4 text-muted">{t('demos.noRounds')}</p>
      </div>
    )
  }

  return (
    <>
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('demos.summary')}</h2>
        <p className="my-4 text-muted">
          {t('demos.siteDistribution')}:{' '}
          {siteCounts.map(([s, n]) => (
            <span key={s} className="mr-1.5 inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">
              {s}: {n}
            </span>
          ))}
        </p>
        <p className="my-4 text-muted">
          {t('demos.totalUtility')}: <strong>{totalUtility}</strong>
          <span className="ml-4">
            {t('demos.rounds')}: <strong>{rounds.length}</strong>
          </span>
        </p>
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('demos.rounds')}</h2>
        <table className="w-full border-collapse text-[0.9rem]">
          <thead>
            <tr>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">#</th>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.result', 'Resultado')}</th>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.buy')}</th>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.site')}</th>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.utility')}</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((r) => (
              <tr key={r.id}>
                <td className="border-b border-border px-2.5 py-2 text-left">{r.round_number}</td>
                <td className="border-b border-border px-2.5 py-2 text-left">
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
                <td className="border-b border-border px-2.5 py-2 text-left">
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
                <td className="border-b border-border px-2.5 py-2 text-left">
                  <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{r.target_site}</span>
                </td>
                <td className="border-b border-border px-2.5 py-2 text-left">
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

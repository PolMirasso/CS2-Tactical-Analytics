import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SITE_COLOR } from '@/lib/colors'
import type { BuyType, SiteDistributionParams } from '@/types/api'
import { useMaps } from '@/features/maps/hooks'
import { MultiSelect } from '@/components/MultiSelect'
import { useSiteDistribution, useTeamRoster, useTeams } from './hooks'
import { RosterChangeWarning } from './RosterChangeWarning'

const BUY_TYPES: BuyType[] = [
  'pistol', 'full_eco', 'eco', 'ak_hero', 'm4_hero', 'awp_hero', 'force', 'full',
]

const pct = (v: number) => `${(v * 100).toFixed(0)}%`

export function AnalyticsPage() {
  const { t } = useTranslation()
  const { data: maps } = useMaps()
  const [mapId, setMapId] = useState('')
  const [teamIds, setTeamIds] = useState<string[]>([])
  const [buyTypes, setBuyTypes] = useState<BuyType[]>([])

  useEffect(() => {
    if (!mapId && maps && maps.length > 0)
      setMapId((maps.find((m) => m.has_data) ?? maps[0]).id)
  }, [maps, mapId])

  const { data: teams } = useTeams(mapId || undefined)

  const params = useMemo<SiteDistributionParams | undefined>(
    () =>
      mapId
        ? { map_id: mapId, team: teamIds.length ? teamIds : undefined, buy_type: buyTypes.length ? buyTypes : undefined }
        : undefined,
    [mapId, teamIds, buyTypes],
  )
  const { data, isLoading, isError } = useSiteDistribution(params)
  // Roster continuity is a single-team notion; only surface it when one is picked.
  const soloTeam = teamIds.length === 1 ? teamIds[0] : undefined
  const { data: roster } = useTeamRoster(mapId || undefined, soloTeam)

  const toggleBuy = (b: BuyType) =>
    setBuyTypes((cur) => (cur.includes(b) ? cur.filter((x) => x !== b) : [...cur, b]))

  return (
    <div>
      <h1>{t('analytics.title')}</h1>
      <p className="text-muted">{t('analytics.subtitle')}</p>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <div className="flex flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
          <div>
            <label htmlFor="an-map">{t('demos.map')}</label>
            <select id="an-map" value={mapId} onChange={(e) => { setMapId(e.target.value); setTeamIds([]) }}>
              {(maps ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="an-team">{t('demos.team')}</label>
            <MultiSelect
              id="an-team"
              options={teams ?? []}
              values={teamIds}
              onChange={setTeamIds}
              placeholder={t('analytics.allTeams')}
            />
          </div>
        </div>

        <label>{t('demos.buy')}</label>
        <div className="flex flex-wrap gap-3">
          {BUY_TYPES.map((b) => (
            <label key={b} className="flex items-center gap-1 font-normal whitespace-nowrap">
              <input type="checkbox" checked={buyTypes.includes(b)} onChange={() => toggleBuy(b)} />
              {t(`demos.buyTypes.${b}`)}
            </label>
          ))}
        </div>
      </div>

      {soloTeam && roster?.has_changes && <RosterChangeWarning roster={roster} />}

      {isLoading && <p className="text-muted">{t('common.loading')}</p>}
      {isError && <p className="my-2 text-[0.9rem] text-danger">{t('common.error')}</p>}

      {data && (
        <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
          <h2>{t('analytics.siteDistribution')}</h2>
          {data.total_rounds === 0 ? (
            <p className="text-muted">{t('analytics.noData')}</p>
          ) : (
            <>
              <p className="text-muted">
                {t('analytics.summary', {
                  rounds: data.total_rounds,
                  demos: data.total_demos,
                  winRate: pct(data.overall_win_rate),
                })}
              </p>
              <div className="mt-3 flex flex-col gap-2.5">
                {data.sites.map((s) => (
                  <div key={s.site}>
                    <div className="flex justify-between text-sm">
                      <span><span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{s.site}</span> {s.rounds} ({pct(s.pct)})</span>
                      <span className="text-muted">{t('analytics.winRate')}: {s.rounds ? pct(s.win_rate) : '-'}</span>
                    </div>
                    <div className="mt-0.5 h-3.5 rounded bg-[#1f2937]">
                      <div
                        className="h-full rounded"
                        style={{
                          width: pct(s.pct),
                          background: SITE_COLOR[s.site] ?? '#888',
                          minWidth: s.rounds ? 2 : 0,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

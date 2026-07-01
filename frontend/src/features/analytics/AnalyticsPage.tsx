import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { BuyType, SiteDistributionParams } from '@/types/api'
import { useMaps } from '@/features/maps/hooks'
import { useSiteDistribution, useTeams } from './hooks'

const BUY_TYPES: BuyType[] = [
  'pistol', 'full_eco', 'eco', 'ak_hero', 'm4_hero', 'awp_hero', 'force', 'full',
]

const SITE_COLOR: Record<string, string> = {
  A: '#f59e0b', B: '#3b82f6', Mid: '#10b981', NoPlant: '#6b7280',
}

const pct = (v: number) => `${(v * 100).toFixed(0)}%`

export function AnalyticsPage() {
  const { t } = useTranslation()
  const { data: maps } = useMaps()
  const [mapId, setMapId] = useState('')
  const [team, setTeam] = useState('')
  const [buyTypes, setBuyTypes] = useState<BuyType[]>([])

  useEffect(() => {
    if (!mapId && maps && maps.length > 0) setMapId(maps[0].id)
  }, [maps, mapId])

  const { data: teams } = useTeams(mapId || undefined)

  const params = useMemo<SiteDistributionParams | undefined>(
    () =>
      mapId
        ? { map_id: mapId, team: team || undefined, buy_type: buyTypes.length ? buyTypes : undefined }
        : undefined,
    [mapId, team, buyTypes],
  )
  const { data, isLoading, isError } = useSiteDistribution(params)

  const toggleBuy = (b: BuyType) =>
    setBuyTypes((cur) => (cur.includes(b) ? cur.filter((x) => x !== b) : [...cur, b]))

  return (
    <div>
      <h1>{t('analytics.title')}</h1>
      <p className="muted">{t('analytics.subtitle')}</p>

      <div className="card">
        <div className="row">
          <div>
            <label htmlFor="an-map">{t('demos.map')}</label>
            <select id="an-map" value={mapId} onChange={(e) => { setMapId(e.target.value); setTeam('') }}>
              {(maps ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="an-team">{t('demos.team')}</label>
            <select id="an-team" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">{t('analytics.allTeams')}</option>
              {(teams ?? []).map((tm) => (
                <option key={tm} value={tm}>{tm}</option>
              ))}
            </select>
          </div>
        </div>

        <label>{t('demos.buy')}</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {BUY_TYPES.map((b) => (
            <label key={b} style={{ display: 'flex', alignItems: 'center', gap: 4, fontWeight: 'normal', whiteSpace: 'nowrap' }}>
              <input type="checkbox" checked={buyTypes.includes(b)} onChange={() => toggleBuy(b)} />
              {t(`demos.buyTypes.${b}`)}
            </label>
          ))}
        </div>
      </div>

      {isLoading && <p className="muted">{t('common.loading')}</p>}
      {isError && <p className="error">{t('common.error')}</p>}

      {data && (
        <div className="card">
          <h2>{t('analytics.siteDistribution')}</h2>
          {data.total_rounds === 0 ? (
            <p className="muted">{t('analytics.noData')}</p>
          ) : (
            <>
              <p className="muted">
                {t('analytics.summary', {
                  rounds: data.total_rounds,
                  demos: data.total_demos,
                  winRate: pct(data.overall_win_rate),
                })}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
                {data.sites.map((s) => (
                  <div key={s.site}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                      <span><span className="badge">{s.site}</span> {s.rounds} ({pct(s.pct)})</span>
                      <span className="muted">{t('analytics.winRate')}: {s.rounds ? pct(s.win_rate) : '-'}</span>
                    </div>
                    <div style={{ background: '#1f2937', borderRadius: 4, height: 14, marginTop: 2 }}>
                      <div
                        style={{
                          width: pct(s.pct),
                          height: '100%',
                          background: SITE_COLOR[s.site] ?? '#888',
                          borderRadius: 4,
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

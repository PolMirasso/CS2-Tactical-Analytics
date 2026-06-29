import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { BuyType, PredictOut, Site, UtilityType, ZoneOut } from '@/types/api'
import { useAuth } from '@/features/auth/AuthContext'
import { useTeams } from '@/features/analytics/hooks'
import { useMaps } from '@/features/maps/hooks'
import { ScoutingRadar, UTIL_COLOR, type DrawnRect, type Token } from './ScoutingRadar'
import { ScoutingTimeline } from './ScoutingTimeline'
import { fmtClock } from './clock'
import { useModelStatus, usePredict, useTendencies, useTrainModel } from './hooks'

const UTILS: UtilityType[] = ['smoke', 'flash', 'molotov', 'he']
const BUY_TYPES: BuyType[] = ['pistol', 'eco', 'force', 'full']
const SITE_ORDER: Site[] = ['A', 'B', 'NoPlant']
const SITE_COLOR: Record<string, string> = {
  A: '#f59e0b', B: '#3b82f6', Mid: '#10b981', NoPlant: '#6b7280',
}
const BUY_EQUIP: Record<string, number> = {
  pistol: 4000, eco: 6000, force: 12000, full: 22000,
}

const pct = (v: number) => `${(v * 100).toFixed(0)}%`
const makeId = () => `${Date.now()}-${Math.round(Math.random() * 1e6)}`
const clampS = (v: number) => Math.max(0, Math.min(Math.round(v || 0), 115))

export function ScoutingPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const { data: maps } = useMaps()
  const [mapId, setMapId] = useState('')
  const [team, setTeam] = useState('')
  const [buyType, setBuyType] = useState<BuyType>('full')
  const [tokens, setTokens] = useState<Token[]>([])
  const [activeUtil, setActiveUtil] = useState<UtilityType>('smoke')
  const [activeFrom, setActiveFrom] = useState(5)
  const [activeTo, setActiveTo] = useState(15)
  const setActiveWindow = (from: number, to: number) => { setActiveFrom(clampS(from)); setActiveTo(clampS(to)) }

  useEffect(() => {
    if (!mapId && maps && maps.length > 0) setMapId(maps[0].id)
  }, [maps, mapId])

  const { data: teams } = useTeams(mapId || undefined)
  const map = useMemo(() => maps?.find((m) => m.id === mapId) ?? null, [maps, mapId])
  const zones: ZoneOut[] = map?.zones ?? []

  const tendencies = useTendencies(mapId || undefined, team || undefined)
  const modelStatus = useModelStatus()
  const predict = usePredict()
  const trainModel = useTrainModel()

  // Reset the board when the map changes (zones differ between maps).
  useEffect(() => {
    setTokens([])
    predict.reset()
  }, [mapId]) // eslint-disable-line react-hooks/exhaustive-deps

  const addDrawnZone = (rect: DrawnRect) => {
    setTokens((ts) => [
      ...ts,
      {
        id: makeId(),
        util_type: activeUtil,
        time_from: activeFrom,
        time_to: activeTo,
        x: rect.x,
        y: rect.y,
        w: rect.w,
        h: rect.h,
      },
    ])
  }
  const removeToken = (id: string) => setTokens((ts) => ts.filter((tk) => tk.id !== id))

  const setTokenWindow = (id: string, from: number, to: number) =>
    setTokens((ts) => ts.map((tk) =>
      tk.id === id ? { ...tk, time_from: clampS(from), time_to: clampS(to) } : tk,
    ))

  const analyze = () => {
    if (!mapId) return
    predict.mutate({
      map_id: mapId,
      team: team || undefined,
      buy_type: buyType,
      equip_value: BUY_EQUIP[buyType] ?? 0,
      utility: tokens.map((tk) => ({
        util_type: tk.util_type,
        x: tk.x,
        y: tk.y,
        w: tk.w,
        h: tk.h,
        time_from: tk.time_from,
        time_to: tk.time_to,
        side: 't',
      })),
    })
  }

  const result = predict.data
  const ms = modelStatus.data

  return (
    <div>
      <h1>{t('scouting.title')}</h1>
      <p className="muted">{t('scouting.subtitle')}</p>

      <div className="print-only" style={{ marginBottom: 12 }}>
        <h2 style={{ marginBottom: 4 }}>
          {t('scouting.reportTitle')}: {team || t('analytics.allTeams')} — {map?.name ?? mapId}
        </h2>
        <p className="muted">{t('demos.buy')}: {t(`demos.buyTypes.${buyType}`)}</p>
      </div>

      {/* Controls */}
      <div className="card no-print">
        <div className="row">
          <div>
            <label htmlFor="sc-map">{t('demos.map')}</label>
            <select id="sc-map" value={mapId} onChange={(e) => { setMapId(e.target.value); setTeam('') }}>
              {(maps ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="sc-team">{t('scouting.team')}</label>
            <select id="sc-team" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">{t('analytics.allTeams')}</option>
              {(teams ?? []).map((tm) => (
                <option key={tm} value={tm}>{tm}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="sc-buy">{t('demos.buy')}</label>
            <select id="sc-buy" value={buyType} onChange={(e) => setBuyType(e.target.value as BuyType)}>
              {BUY_TYPES.map((b) => (
                <option key={b} value={b}>{t(`demos.buyTypes.${b}`)}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
          <ModelChip
            trained={!!ms?.trained}
            label={
              ms?.trained
                ? t('scouting.trained', { rounds: ms.n_rounds, acc: ms.accuracy != null ? pct(ms.accuracy) : '—' })
                : t('scouting.untrained')
            }
          />
          {ms?.trained && ms.baseline_accuracy != null && (
            <span className="muted" style={{ fontSize: 12 }}>
              {t('scouting.baselineAccuracy')}: {pct(ms.baseline_accuracy)}
            </span>
          )}
          {ms?.trained && ms.params?.layers && (
            <span className="muted" style={{ fontSize: 12 }}>
              {t('scouting.network')}: {ms.params.layers} · α {ms.params.alpha}
            </span>
          )}
          {isAdmin && (
            <button className="ghost" onClick={() => trainModel.mutate()} disabled={trainModel.isPending}>
              {trainModel.isPending ? t('common.loading') : t('scouting.train')}
            </button>
          )}
        </div>
      </div>

      {/* Tactical board */}
      <div className="card">
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 480px', minWidth: 320 }}>
            <div className="no-print" style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                {UTILS.map((u) => (
                  <button
                    key={u}
                    onClick={() => setActiveUtil(u)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      background: activeUtil === u ? UTIL_COLOR[u] : 'transparent',
                      color: activeUtil === u ? '#11141a' : 'var(--text)',
                      border: `1px solid ${UTIL_COLOR[u]}`,
                      fontWeight: 600,
                    }}
                  >
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: UTIL_COLOR[u] }} />
                    {t(`scouting.utilTypes.${u}`)}
                  </button>
                ))}
              </div>
              <label style={{ marginBottom: 4, display: 'block' }}>{t('scouting.timeWindow')}</label>
              <ScoutingTimeline
                tokens={tokens}
                activeUtil={activeUtil}
                activeFrom={activeFrom}
                activeTo={activeTo}
                drawColor={UTIL_COLOR[activeUtil]}
                onActive={setActiveWindow}
                onToken={setTokenWindow}
              />
              <p className="muted" style={{ margin: '6px 0 0', fontSize: 13 }}>{t('scouting.addHint')}</p>
            </div>
            {map ? (
              <ScoutingRadar
                mapId={map.id}
                tokens={tokens}
                onDrawZone={addDrawnZone}
                onRemoveToken={removeToken}
                drawColor={UTIL_COLOR[activeUtil]}
              />
            ) : (
              <p className="muted">{t('common.loading')}</p>
            )}
          </div>

          {/* Setup list + prediction */}
          <div style={{ flex: '1 1 320px', minWidth: 280, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div className="no-print">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ margin: 0 }}>{t('scouting.placed')} ({tokens.length})</h2>
                {tokens.length > 0 && (
                  <button className="ghost" onClick={() => setTokens([])}>{t('scouting.clear')}</button>
                )}
              </div>
              {tokens.length === 0 ? (
                <p className="muted">{t('scouting.noTokens')}</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                  {tokens.map((tk) => (
                    <div
                      key={tk.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 8px',
                        background: '#11141a',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                      }}
                    >
                      <span style={{ width: 12, height: 12, borderRadius: 3, background: UTIL_COLOR[tk.util_type], flexShrink: 0 }} />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 }}>
                        {t(`scouting.utilTypes.${tk.util_type}`)}
                      </span>
                      <span className="muted" style={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
                        {fmtClock(tk.time_from)}–{fmtClock(tk.time_to)}
                      </span>
                      <button className="ghost" style={{ padding: '2px 8px' }} onClick={() => removeToken(tk.id)}>✕</button>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={analyze}
                disabled={!mapId || tokens.length === 0 || predict.isPending}
                style={{ marginTop: 10, width: '100%' }}
              >
                {predict.isPending ? t('common.loading') : t('scouting.analyze')}
              </button>
            </div>

            {result && <Prediction result={result} />}
          </div>
        </div>
      </div>

      {/* Historical tendencies + utility heatmap */}
      <div className="card">
        <h2>{t('scouting.tendencies')}{team ? ` · ${team}` : ''}</h2>
        {tendencies.isLoading && <p className="muted">{t('common.loading')}</p>}
        {tendencies.data && tendencies.data.total_rounds === 0 && (
          <p className="muted">{t('scouting.noTendencies')}</p>
        )}
        {tendencies.data && tendencies.data.total_rounds > 0 && (
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <div style={{ flex: '1 1 260px', minWidth: 240 }}>
              <p className="muted" style={{ marginTop: 0 }}>
                {t('scouting.tendenciesSummary', { rounds: tendencies.data.total_rounds })}
              </p>
              {tendencies.data.sites.map((s) => (
                <Bar key={s.site} label={s.site} value={s.pct} color={SITE_COLOR[s.site] ?? '#888'} note={`${s.rounds}`} />
              ))}
            </div>
            {map && (
              <div style={{ flex: '0 1 420px' }}>
                <p className="muted" style={{ marginTop: 0 }}>{t('scouting.heatmap')}</p>
                <ScoutingRadar mapId={map.id} zones={zones} heatmap={tendencies.data.heatmap} size={420} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="no-print" style={{ marginBottom: 24 }}>
        <button className="ghost" onClick={() => window.print()}>{t('scouting.exportPdf')}</button>
      </div>
    </div>
  )
}

function ModelChip({ trained, label }: { trained: boolean; label: string }) {
  return (
    <span className={`badge ${trained ? 'ok' : 'pending'}`}>{label}</span>
  )
}

function Bar({ label, value, color, note }: { label: string; value: number; color: string; note?: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
        <span><span className="badge">{label}</span> {note && <span className="muted">{note}</span>}</span>
        <span>{(value * 100).toFixed(0)}%</span>
      </div>
      <div style={{ background: '#1f2937', borderRadius: 4, height: 14, marginTop: 2 }}>
        <div style={{ width: `${value * 100}%`, height: '100%', background: color, borderRadius: 4, minWidth: value > 0 ? 2 : 0 }} />
      </div>
    </div>
  )
}

function Prediction({ result }: { result: PredictOut }) {
  const { t } = useTranslation()
  const baseline = new Map(result.baseline.map((b) => [b.site, b.prob]))
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>{t('scouting.prediction')}</h2>
        <span className={`badge ${result.source === 'model' ? 'ok' : 'pending'}`}>
          {result.source === 'model' ? t('scouting.modelSource') : t('scouting.baselineSource')}
        </span>
      </div>
      <p style={{ margin: '0 0 12px' }}>
        {t('scouting.predictedSite')}:{' '}
        <strong style={{ color: SITE_COLOR[result.predicted_site] ?? 'var(--text)', fontSize: 18 }}>
          {result.predicted_site}
        </strong>{' '}
        <span className="muted">({(result.confidence * 100).toFixed(0)}%)</span>
      </p>
      {SITE_ORDER.map((s) => {
        const prob = result.sites.find((x) => x.site === s)?.prob ?? 0
        const base = baseline.get(s) ?? 0
        return (
          <div key={s} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
              <span className="badge">{s}</span>
              <span>
                {(prob * 100).toFixed(0)}%{' '}
                <span className="muted" title={t('scouting.baseline')}>({(base * 100).toFixed(0)}%)</span>
              </span>
            </div>
            <div style={{ position: 'relative', background: '#1f2937', borderRadius: 4, height: 14, marginTop: 2 }}>
              <div style={{ width: `${prob * 100}%`, height: '100%', background: SITE_COLOR[s] ?? '#888', borderRadius: 4, minWidth: prob > 0 ? 2 : 0 }} />
              {/* Baseline marker: a tick at the historical frequency. */}
              <div
                title={t('scouting.baseline')}
                style={{ position: 'absolute', top: -2, bottom: -2, left: `${base * 100}%`, width: 2, background: 'var(--text)' }}
              />
            </div>
          </div>
        )
      })}
      <p className="muted" style={{ fontSize: 12, margin: '6px 0 0' }}>{t('scouting.baselineHint')}</p>
    </div>
  )
}

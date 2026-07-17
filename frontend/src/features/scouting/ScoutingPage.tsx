import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { BuyType, MapOut, PerMapMetric, PredictOut, ReliabilityBin, Site, UtilityType, ZoneOut } from '@/types/api'
import { useAuth } from '@/features/auth/AuthContext'
import { useTeamRoster, useTeams } from '@/features/analytics/hooks'
import { RosterChangeWarning } from '@/features/analytics/RosterChangeWarning'
import { useMaps } from '@/features/maps/hooks'
import { SearchSelect } from '@/components/SearchSelect'
import { SITE_COLOR, UTIL_COLOR } from '@/lib/colors'
import { ScoutingRadar, type DrawnRect, type Token } from './ScoutingRadar'
import { ScoutingTimeline } from './ScoutingTimeline'
import { fmtClock } from './clock'
import { useModelStatus, usePredict, useTendencies, useTrainModel } from './hooks'

const UTILS: UtilityType[] = ['smoke', 'flash', 'molotov', 'he']
const BUY_TYPES: BuyType[] = ['pistol', 'eco', 'force', 'full']
const SITE_ORDER: Site[] = ['A', 'B', 'NoPlant']
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
    if (!mapId && maps && maps.length > 0)
      setMapId((maps.find((m) => m.has_data) ?? maps[0]).id)
  }, [maps, mapId])

  const { data: teams } = useTeams(mapId || undefined)
  const map = useMemo(() => maps?.find((m) => m.id === mapId) ?? null, [maps, mapId])
  const teamName = useMemo(
    () => teams?.find((tm) => tm.id === team)?.name ?? '',
    [teams, team],
  )
  const zones: ZoneOut[] = map?.zones ?? []

  const { data: roster } = useTeamRoster(mapId || undefined, team || undefined)
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
      <p className="text-muted">{t('scouting.subtitle')}</p>

      {team && roster?.has_changes && <RosterChangeWarning roster={roster} />}

      <div className="mb-3 hidden print:block">
        <h2 className="mb-1">
          {t('scouting.reportTitle')}: {teamName || t('analytics.allTeams')} — {map?.name ?? mapId}
        </h2>
        <p className="text-muted">{t('demos.buy')}: {t(`demos.buyTypes.${buyType}`)}</p>
      </div>

      {/* Controls */}
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid print:hidden">
        <div className="flex flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
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
            <SearchSelect
              id="sc-team"
              options={teams ?? []}
              value={team}
              onChange={setTeam}
              allLabel={t('analytics.allTeams')}
            />
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

        <div className="mt-1 flex flex-wrap items-center gap-3">
          <ModelChip
            trained={!!ms?.trained}
            label={
              ms?.trained
                ? t('scouting.trained', { rounds: ms.n_rounds, acc: ms.accuracy != null ? pct(ms.accuracy) : '—' })
                : t('scouting.untrained')
            }
          />
          {ms?.trained && ms.site_accuracy != null && (
            <span className="text-muted text-xs">
              {t('scouting.siteAccuracy')}: {pct(ms.site_accuracy)}
            </span>
          )}
          {ms?.trained && ms.baseline_accuracy != null && (
            <span className="text-muted text-xs">
              {t('scouting.baselineAccuracy')}: {pct(ms.baseline_accuracy)}
            </span>
          )}
          {ms?.trained && ms.params?.site && (
            <span className="text-muted text-xs">
              {t('scouting.network')}: gate {ms.params.gate} · site {ms.params.site} · α {ms.params.alpha}
            </span>
          )}
          {ms?.trained && ms.ece != null && (
            <span className="text-muted text-xs">
              {t('scouting.calibration')}: ECE {pct(ms.ece_uncalibrated ?? ms.ece)} → {pct(ms.ece)}
              {ms.params?.gate_T && ` · T ${ms.params.gate_T}/${ms.params.site_T}`}
            </span>
          )}
          {isAdmin && (
            <button className="border border-border bg-transparent text-text" onClick={() => trainModel.mutate()} disabled={trainModel.isPending}>
              {trainModel.isPending ? t('common.loading') : t('scouting.train')}
            </button>
          )}
        </div>
        {ms?.trained && ms.per_map && ms.per_map.length > 0 && (
          <PerMapTable rows={ms.per_map} maps={maps} />
        )}
        {ms?.trained && ms.reliability && ms.reliability.length > 0 && (
          <ReliabilityDiagram bins={ms.reliability} />
        )}
      </div>

      {/* Tactical board */}
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <div className="flex flex-wrap items-start gap-5">
          <div className="min-w-[320px] flex-[1_1_620px]">
            <div className="print:hidden mb-2.5">
              <div className="mb-2 flex flex-wrap gap-2">
                {UTILS.map((u) => (
                  <button
                    key={u}
                    onClick={() => setActiveUtil(u)}
                    className={`flex items-center gap-1.5 border font-semibold ${
                      activeUtil === u ? 'text-[#11141a]' : 'bg-transparent text-text'
                    }`}
                    style={{
                      background: activeUtil === u ? UTIL_COLOR[u] : undefined,
                      borderColor: UTIL_COLOR[u],
                    }}
                  >
                    <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: UTIL_COLOR[u] }} />
                    {t(`scouting.utilTypes.${u}`)}
                  </button>
                ))}
              </div>
              <label className="mb-1 block">{t('scouting.timeWindow')}</label>
              <ScoutingTimeline
                tokens={tokens}
                activeUtil={activeUtil}
                activeFrom={activeFrom}
                activeTo={activeTo}
                drawColor={UTIL_COLOR[activeUtil]}
                onActive={setActiveWindow}
                onToken={setTokenWindow}
              />
              <p className="mt-1.5 mb-0 text-[13px] text-muted">{t('scouting.addHint')}</p>
            </div>
            {map ? (
              <ScoutingRadar
                mapId={map.id}
                tokens={tokens}
                onDrawZone={addDrawnZone}
                onRemoveToken={removeToken}
                drawColor={UTIL_COLOR[activeUtil]}
                size={720}
              />
            ) : (
              <p className="text-muted">{t('common.loading')}</p>
            )}
          </div>

          {/* Setup list + prediction */}
          <div className="flex min-w-[280px] flex-[1_1_320px] flex-col gap-3.5">
            <div className="print:hidden">
              <div className="flex items-center justify-between">
                <h2 className="m-0">{t('scouting.placed')} ({tokens.length})</h2>
                {tokens.length > 0 && (
                  <button className="border border-border bg-transparent text-text" onClick={() => setTokens([])}>{t('scouting.clear')}</button>
                )}
              </div>
              {tokens.length === 0 ? (
                <p className="text-muted">{t('scouting.noTokens')}</p>
              ) : (
                <div className="mt-2 flex flex-col gap-1.5">
                  {tokens.map((tk) => (
                    <div
                      key={tk.id}
                      className="flex items-center gap-2 rounded-md border border-border bg-[#11141a] px-2 py-1.5"
                    >
                      <span className="h-3 w-3 shrink-0 rounded-[3px]" style={{ background: UTIL_COLOR[tk.util_type] }} />
                      <span className="flex-1 overflow-hidden text-[13px] text-ellipsis whitespace-nowrap">
                        {t(`scouting.utilTypes.${tk.util_type}`)}
                      </span>
                      <span className="text-xs text-muted tabular-nums">
                        {fmtClock(tk.time_from)}–{fmtClock(tk.time_to)}
                      </span>
                      <button className="border border-border bg-transparent text-text px-2 py-0.5" onClick={() => removeToken(tk.id)}>✕</button>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={analyze}
                disabled={!mapId || tokens.length === 0 || predict.isPending}
                className="mt-2.5 w-full"
              >
                {predict.isPending ? t('common.loading') : t('scouting.analyze')}
              </button>
            </div>

            {result && <Prediction result={result} />}
          </div>
        </div>
      </div>

      {/* Historical tendencies + utility heatmap */}
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('scouting.tendencies')}{teamName ? ` · ${teamName}` : ''}</h2>
        {tendencies.isLoading && <p className="text-muted">{t('common.loading')}</p>}
        {tendencies.data && tendencies.data.total_rounds === 0 && (
          <p className="text-muted">{t('scouting.noTendencies')}</p>
        )}
        {tendencies.data && tendencies.data.total_rounds > 0 && (
          <div className="flex flex-wrap items-start gap-6">
            <div className="min-w-[240px] flex-[1_1_260px]">
              <p className="text-muted mt-0">
                {t('scouting.tendenciesSummary', { rounds: tendencies.data.total_rounds })}
              </p>
              {tendencies.data.sites.map((s) => (
                <Bar key={s.site} label={s.site} value={s.pct} color={SITE_COLOR[s.site] ?? '#888'} note={`${s.rounds}`} />
              ))}
            </div>
            {map && (
              <div className="flex-[0_1_420px]">
                <p className="text-muted mt-0">{t('scouting.heatmap')}</p>
                <ScoutingRadar mapId={map.id} zones={zones} heatmap={tendencies.data.heatmap} size={420} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mb-6 print:hidden">
        <button className="border border-border bg-transparent text-text" onClick={() => window.print()}>{t('scouting.exportPdf')}</button>
      </div>
    </div>
  )
}

function ModelChip({ trained, label }: { trained: boolean; label: string }) {
  return (
    <span
      className={`inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs ${
        trained ? 'border-ok text-ok' : 'border-warn text-warn'
      }`}
    >
      {label}
    </span>
  )
}

function Bar({ label, value, color, note }: { label: string; value: number; color: string; note?: string }) {
  return (
    <div className="mb-2.5">
      <div className="flex justify-between text-sm">
        <span><span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{label}</span> {note && <span className="text-muted">{note}</span>}</span>
        <span>{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="mt-0.5 h-3.5 rounded bg-[#1f2937]">
        <div
          className="h-full rounded"
          style={{ width: `${value * 100}%`, background: color, minWidth: value > 0 ? 2 : 0 }}
        />
      </div>
    </div>
  )
}

// per-map held-out accuracy table
function PerMapTable({ rows, maps }: { rows: PerMapMetric[]; maps?: MapOut[] }) {
  const { t } = useTranslation()
  const name = (id: string) => maps?.find((m) => m.id === id)?.name ?? id
  const cell = 'py-0.5 pr-2.5 pl-0 text-right whitespace-nowrap'
  const head = `${cell} border-b border-border font-semibold`
  return (
    <div className="mt-3 overflow-x-auto print:hidden">
      <div className="text-muted mb-1 text-xs">{t('scouting.byMap')}</div>
      <table className="border-collapse text-xs">
        <thead>
          <tr className="text-muted">
            <th className={`${head} text-left`}>{t('scouting.map')}</th>
            <th className={head}>{t('scouting.plants')}</th>
            <th className={head}>{t('scouting.siteAccShort')}</th>
            <th className={head}>{t('scouting.baselineShort')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.map_id}>
              <td className={`${cell} text-left`}>{name(r.map_id)}</td>
              <td className={cell}>{r.n_plant}</td>
              <td className={cell}>{r.site_accuracy != null ? pct(r.site_accuracy) : '—'}</td>
              <td className={`${cell} text-muted`}>{r.baseline_accuracy != null ? pct(r.baseline_accuracy) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// calibration plot
function ReliabilityDiagram({ bins }: { bins: ReliabilityBin[] }) {
  const { t } = useTranslation()
  const P = { l: 22, r: 10, t: 10, b: 26 }
  const S = 150
  const w = P.l + S + P.r
  const h = P.t + S + P.b
  const X = (c: number) => P.l + c * S
  const Y = (a: number) => P.t + (1 - a) * S
  const pts = [...bins].sort((a, b) => a.confidence - b.confidence)
  const maxCount = Math.max(1, ...pts.map((b) => b.count))
  const line = pts.map((b) => `${X(b.confidence).toFixed(1)},${Y(b.accuracy).toFixed(1)}`).join(' ')
  return (
    <div className="print:hidden mt-3">
      <div className="text-muted mb-1 text-xs">{t('scouting.reliabilityTitle')}</div>
      <svg width={w} height={h} role="img" aria-label={t('scouting.reliabilityTitle')} className="max-w-full">
        <rect x={P.l} y={P.t} width={S} height={S} fill="none" className="stroke-border" />
        <line x1={X(0.5)} y1={P.t} x2={X(0.5)} y2={P.t + S} className="stroke-border" strokeDasharray="2 3" opacity={0.6} />
        <line x1={P.l} y1={Y(0.5)} x2={P.l + S} y2={Y(0.5)} className="stroke-border" strokeDasharray="2 3" opacity={0.6} />
        <line x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} className="stroke-muted" strokeDasharray="4 3" />
        {pts.length > 1 && <polyline points={line} fill="none" strokeWidth={2} className="stroke-accent" />}
        {pts.map((b, i) => (
          <circle
            key={i}
            cx={X(b.confidence)}
            cy={Y(b.accuracy)}
            r={4 + 3 * (b.count / maxCount)}
            className="fill-accent stroke-bg"
            strokeWidth={1.5}
          >
            <title>{`${t('scouting.confidence')} ${pct(b.confidence)} · ${t('scouting.observed')} ${pct(b.accuracy)} · n=${b.count}`}</title>
          </circle>
        ))}
        <text x={P.l + S / 2} y={h - 3} fontSize={10} className="fill-muted" textAnchor="middle">{t('scouting.confidence')}</text>
        <text x={9} y={P.t + S / 2} fontSize={10} className="fill-muted" textAnchor="middle" transform={`rotate(-90 9 ${P.t + S / 2})`}>{t('scouting.observed')}</text>
      </svg>
      <div className="text-muted text-[11px]">{t('scouting.reliabilityHint')}</div>
    </div>
  )
}

function Prediction({ result }: { result: PredictOut }) {
  const { t } = useTranslation()
  const baseline = new Map(result.baseline.map((b) => [b.site, b.prob]))
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-2.5 flex flex-wrap items-center gap-2.5">
        <h2 className="m-0">{t('scouting.prediction')}</h2>
        <span
          className={`inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs ${
            result.source === 'model' ? 'border-ok text-ok' : 'border-warn text-warn'
          }`}
        >
          {result.source === 'model' ? t('scouting.modelSource') : t('scouting.baselineSource')}
        </span>
      </div>
      <p className="mt-0 mb-3">
        {t('scouting.predictedSite')}:{' '}
        <strong className="text-[18px]" style={{ color: SITE_COLOR[result.predicted_site] ?? 'var(--color-text)' }}>
          {result.predicted_site}
        </strong>{' '}
        <span className="text-muted">({(result.confidence * 100).toFixed(0)}%)</span>
      </p>
      {SITE_ORDER.map((s) => {
        const prob = result.sites.find((x) => x.site === s)?.prob ?? 0
        const base = baseline.get(s) ?? 0
        return (
          <div key={s} className="mb-2.5">
            <div className="flex justify-between text-sm">
              <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{s}</span>
              <span>
                {(prob * 100).toFixed(0)}%{' '}
                <span className="text-muted" title={t('scouting.baseline')}>({(base * 100).toFixed(0)}%)</span>
              </span>
            </div>
            <div className="relative mt-0.5 h-3.5 rounded bg-[#1f2937]">
              <div
                className="h-full rounded"
                style={{ width: `${prob * 100}%`, background: SITE_COLOR[s] ?? '#888', minWidth: prob > 0 ? 2 : 0 }}
              />
              {/* Baseline marker: a tick at the historical frequency. */}
              <div
                title={t('scouting.baseline')}
                className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-text"
                style={{ left: `${base * 100}%` }}
              />
            </div>
          </div>
        )
      })}
      <p className="mt-1.5 mb-0 text-xs text-muted">{t('scouting.baselineHint')}</p>
    </div>
  )
}

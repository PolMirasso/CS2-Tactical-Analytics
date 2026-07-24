import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { BuyType, MapOut, PerMapMetric, PredictOut, ReliabilityBin, Site, Timing, UtilityType, ZoneOut } from '@/types/api'
import { useAuth } from '@/features/auth/AuthContext'
import { useTeamRoster, useTeams } from '@/features/analytics/hooks'
import { RosterChangeWarning } from '@/features/analytics/RosterChangeWarning'
import { useMaps } from '@/features/maps/hooks'
import { MultiSelect } from '@/components/MultiSelect'
import { SITE_COLOR, TIMING_COLOR, UTIL_COLOR } from '@/lib/colors'
import { WEAPON_CATEGORIES, WEAPON_IDS, WEAPON_LABELS } from '@/lib/weapons'
import { ScoutingRadar, type DrawnRect, type Token } from './ScoutingRadar'
import { ScoutingTimeline } from './ScoutingTimeline'
import { fmtClock } from './clock'
import { useEvaluateMaps, useModelStatus, usePredict, useTendencies, useTrainModel } from './hooks'

const UTILS: UtilityType[] = ['smoke', 'flash', 'molotov', 'he']
const BUY_TYPES: BuyType[] = ['pistol', 'eco', 'force', 'full']
const SITE_ORDER: Site[] = ['A', 'B', 'NoPlant']
const TIMING_ORDER: Timing[] = ['rush', 'default', 'late']
const BUY_EQUIP: Record<string, number> = {
  pistol: 4000, eco: 6000, force: 12000, full: 22000,
}

interface WeaponPick {
  id: string
  weapon: string
  count: number
}

function WeaponSelect(props: {
  id: string
  value: string
  onChange: (v: string) => void
  placeholder: string
  catLabel: (id: string) => string
  exclude?: Set<string>
  className?: string
  ariaLabel?: string
}) {
  return (
    <select
      id={props.id}
      aria-label={props.ariaLabel}
      className={props.className}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">{props.placeholder}</option>
      {WEAPON_CATEGORIES.map((c) => {
        const ws = c.weapons.filter((w) => !props.exclude?.has(w.id) || w.id === props.value)
        if (ws.length === 0) return null
        return (
          <optgroup key={c.id} label={props.catLabel(c.id)}>
            {ws.map((w) => (
              <option key={w.id} value={w.id}>{w.label}</option>
            ))}
          </optgroup>
        )
      })}
    </select>
  )
}

// Growing list of weapons a side carries: a new empty selector shows up only
function WeaponPicker(props: {
  idPrefix: string
  label: string
  picks: WeaponPick[]
  onChange: (picks: WeaponPick[]) => void
  addLabel: string
  countLabel: string
  removeLabel: string
  hint: string
  catLabel: (id: string) => string
}) {
  const used = new Set(props.picks.map((p) => p.weapon))
  const setWeapon = (id: string, weapon: string) =>
    props.onChange(
      weapon === ''
        ? props.picks.filter((p) => p.id !== id)
        : props.picks.map((p) => (p.id === id ? { ...p, weapon } : p)),
    )
  const setCount = (id: string, count: number) =>
    props.onChange(props.picks.map((p) => (p.id === id ? { ...p, count: clampCount(count) } : p)))
  return (
    <div>
      <label>{props.label}</label>
      <p className="mt-0.5 mb-1 text-xs text-muted">{props.hint}</p>
      <div className="flex flex-col gap-2">
        {props.picks.map((p) => (
          <div key={p.id} className="flex items-center gap-2">
            <WeaponSelect
              id={`${props.idPrefix}-${p.id}`}
              value={p.weapon}
              onChange={(w) => setWeapon(p.id, w)}
              placeholder={props.removeLabel}
              exclude={used}
              catLabel={props.catLabel}
              className="min-w-0 flex-1"
            />
            <span className="flex shrink-0 items-center gap-1 text-sm text-muted" title={props.countLabel}>
              <span aria-hidden="true">≥</span>
              <input
                type="number"
                min={1}
                max={5}
                value={p.count}
                aria-label={props.countLabel}
                onChange={(e) => setCount(p.id, parseInt(e.target.value, 10))}
                className="w-12"
              />
            </span>
            <button
              type="button"
              className="shrink-0 px-1 text-muted hover:text-text"
              aria-label={props.removeLabel}
              onClick={() => setWeapon(p.id, '')}
            >
              ✕
            </button>
          </div>
        ))}
        <WeaponSelect
          id={`${props.idPrefix}-add`}
          value=""
          onChange={(w) => w && props.onChange([...props.picks, { id: makeId(), weapon: w, count: 1 }])}
          placeholder={props.addLabel}
          ariaLabel={props.addLabel}
          exclude={used}
          catLabel={props.catLabel}
        />
      </div>
    </div>
  )
}

const pct = (v: number) => `${(v * 100).toFixed(0)}%`
const makeId = () => `${Date.now()}-${Math.round(Math.random() * 1e6)}`
const clampS = (v: number) => Math.max(0, Math.min(Math.round(v || 0), 115))
const clampCount = (v: number) => Math.max(1, Math.min(5, Math.round(v) || 1))
const weaponSummary = (picks: WeaponPick[]) =>
  picks.map((p) => `${WEAPON_LABELS[p.weapon]}${p.count > 1 ? ` ≥${p.count}` : ''}`).join(', ')

export function ScoutingPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const { data: maps } = useMaps()
  const [mapId, setMapId] = useState('')
  const [teamIds, setTeamIds] = useState<string[]>([])
  const [buyType, setBuyType] = useState<BuyType | ''>('')
  const [oppBuyType, setOppBuyType] = useState<BuyType | ''>('')
  const [teamWeapons, setTeamWeapons] = useState<WeaponPick[]>([])
  const [oppWeapons, setOppWeapons] = useState<WeaponPick[]>([])
  const [showFilters, setShowFilters] = useState(false)
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

  // Prediction is one opponent
  const soloTeam = teamIds.length === 1 ? teamIds[0] : undefined
  const teamLabel = useMemo(
    () => teamIds.map((id) => teams?.find((tm) => tm.id === id)?.name ?? id).join(', '),
    [teams, teamIds],
  )
  const zones: ZoneOut[] = map?.zones ?? []

  const { data: roster } = useTeamRoster(mapId || undefined, soloTeam)
  const tendencies = useTendencies(mapId || undefined, teamIds.length ? teamIds : undefined)
  const modelStatus = useModelStatus()
  const predict = usePredict()
  const trainModel = useTrainModel()
  const evaluateMaps = useEvaluateMaps()

  // Reset the board when the map changes (zones differ between maps).
  const skipResetRef = useRef(false)
  useEffect(() => {
    if (skipResetRef.current) { skipResetRef.current = false; return }
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

  // Save/load the whole board as a JSON file
  const fileRef = useRef<HTMLInputElement>(null)
  const [importErr, setImportErr] = useState('')

  const exportSetup = () => {
    const slug = (s: string) => s.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'setup'
    const json = JSON.stringify({
      kind: 'cs2ta.scouting.v1',
      map_id: mapId,
      teams: teamIds,
      buy_type: buyType,
      opponent_buy_type: oppBuyType,
      team_weapons: teamWeapons.map((p) => ({ weapon: p.weapon, count: p.count })),
      opponent_weapons: oppWeapons.map((p) => ({ weapon: p.weapon, count: p.count })),
      tokens: tokens.map((tk) => ({
        util_type: tk.util_type,
        time_from: tk.time_from,
        time_to: tk.time_to,
        x: tk.x, y: tk.y, w: tk.w, h: tk.h,
      })),
    }, null, 2)
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `scouting-${slug(map?.name ?? mapId)}${teamLabel ? `-${slug(teamLabel)}` : ''}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importSetup = async (file: File) => {
    setImportErr('')
    let data: unknown
    try {
      data = JSON.parse(await file.text())
    } catch {
      setImportErr(t('scouting.importError'))
      return
    }
    if (typeof data !== 'object' || data === null || !Array.isArray((data as Record<string, unknown>).tokens)) {
      setImportErr(t('scouting.importError'))
      return
    }
    const obj = data as Record<string, unknown>

    const fileMap = typeof obj.map_id === 'string' ? obj.map_id : undefined
    if (fileMap && !(maps ?? []).some((m) => m.id === fileMap)) {
      setImportErr(t('scouting.importUnknownMap'))
      return
    }

    const parsed: Token[] = []
    for (const item of obj.tokens as unknown[]) {
      if (typeof item !== 'object' || item === null) continue
      const tk = item as Record<string, unknown>
      if (typeof tk.util_type !== 'string' || !UTILS.includes(tk.util_type as UtilityType)) continue
      const xywh = [tk.x, tk.y, tk.w, tk.h]
      if (!xywh.every((n) => typeof n === 'number' && Number.isFinite(n))) continue
      const [x, y, w, h] = xywh as number[]
      const from = clampS(typeof tk.time_from === 'number' ? tk.time_from : 0)
      const to = clampS(typeof tk.time_to === 'number' ? tk.time_to : 0)
      parsed.push({
        id: makeId(),
        util_type: tk.util_type as UtilityType,
        time_from: Math.min(from, to),
        time_to: Math.max(from, to),
        x: Math.round(x), y: Math.round(y),
        w: Math.round(Math.abs(w)), h: Math.round(Math.abs(h)),
      })
    }
    if (parsed.length === 0) {
      setImportErr(t('scouting.importEmpty'))
      return
    }

    if (fileMap && fileMap !== mapId) {
      skipResetRef.current = true
      setMapId(fileMap)
    }
    const readBuy = (v: unknown): BuyType | '' | null =>
      v === '' ? '' : (typeof v === 'string' && (BUY_TYPES as string[]).includes(v) ? (v as BuyType) : null)
    // Accepts the new [{weapon, count}] shape or the legacy single-weapon string.
    const readWeapons = (v: unknown): WeaponPick[] | null => {
      if (v === undefined) return null
      const items = typeof v === 'string' ? [v] : Array.isArray(v) ? v : null
      if (items === null) return null
      const out: WeaponPick[] = []
      const seen = new Set<string>()
      for (const it of items) {
        const wid = typeof it === 'string' ? it
          : it && typeof it === 'object' && typeof (it as Record<string, unknown>).weapon === 'string'
            ? (it as Record<string, string>).weapon : ''
        const rawCount = it && typeof it === 'object' ? (it as Record<string, unknown>).count : 1
        const count = clampCount(typeof rawCount === 'number' ? rawCount : 1)
        if (WEAPON_IDS.includes(wid) && !seen.has(wid)) {
          seen.add(wid)
          out.push({ id: makeId(), weapon: wid, count })
        }
      }
      return out
    }
    const b = readBuy(obj.buy_type); if (b !== null) setBuyType(b)
    const ob = readBuy(obj.opponent_buy_type); if (ob !== null) setOppBuyType(ob)
    const tw = readWeapons(obj.team_weapons ?? obj.team_weapon); if (tw !== null) setTeamWeapons(tw)
    const ow = readWeapons(obj.opponent_weapons ?? obj.opponent_weapon); if (ow !== null) setOppWeapons(ow)
    if (Array.isArray(obj.teams)) setTeamIds(obj.teams.filter((v): v is string => typeof v === 'string'))
    else if (typeof obj.team === 'string') setTeamIds([obj.team])
    setTokens(parsed)
    predict.reset()
  }

  const analyze = () => {
    if (!mapId) return
    predict.mutate({
      map_id: mapId,
      team: soloTeam,
      buy_type: buyType || null,
      equip_value: buyType ? (BUY_EQUIP[buyType] ?? null) : null,
      opponent_buy_type: oppBuyType || null,
      opponent_equip_value: oppBuyType ? (BUY_EQUIP[oppBuyType] ?? null) : null,
      team_weapons: teamWeapons.length ? teamWeapons.map((p) => p.weapon) : null,
      opponent_weapons: oppWeapons.length ? oppWeapons.map((p) => p.weapon) : null,
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
  // test all maps
  const perMap = evaluateMaps.data?.per_map ?? (ms?.trained ? ms.per_map : null)
  const activeFilterCount =
    [buyType, oppBuyType].filter(Boolean).length + teamWeapons.length + oppWeapons.length

  return (
    <div>
      <h1>{t('scouting.title')}</h1>
      <p className="text-muted">{t('scouting.subtitle')}</p>

      {soloTeam && roster?.has_changes && <RosterChangeWarning roster={roster} />}

      <div className="mb-3 hidden print:block">
        <h2 className="mb-1">
          {t('scouting.reportTitle')}: {teamLabel || t('analytics.allTeams')} — {map?.name ?? mapId}
        </h2>
        <p className="text-muted">
          {[
            buyType && `${t('scouting.teamBuy')}: ${t(`demos.buyTypes.${buyType}`)}`,
            oppBuyType && `${t('scouting.oppBuy')}: ${t(`demos.buyTypes.${oppBuyType}`)}`,
            teamWeapons.length > 0 && `${t('scouting.teamWeapon')}: ${weaponSummary(teamWeapons)}`,
            oppWeapons.length > 0 && `${t('scouting.oppWeapon')}: ${weaponSummary(oppWeapons)}`,
          ].filter(Boolean).join(' · ') || t('scouting.anyFilter')}
        </p>
      </div>

      {/* Controls */}
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid print:hidden">
        <div className="flex flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
          <div>
            <label htmlFor="sc-map">{t('demos.map')}</label>
            <select id="sc-map" value={mapId} onChange={(e) => { setMapId(e.target.value); setTeamIds([]) }}>
              {(maps ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="sc-team">{t('scouting.team')}</label>
            <MultiSelect
              id="sc-team"
              options={teams ?? []}
              values={teamIds}
              onChange={setTeamIds}
              placeholder={t('analytics.allTeams')}
            />
          </div>
        </div>

        <div className="mt-3">
          <button
            type="button"
            className="text-sm text-muted hover:text-text"
            aria-expanded={showFilters}
            onClick={() => setShowFilters((v) => !v)}
          >
            {showFilters ? '▾' : '▸'} {t('scouting.filters')}
            {activeFilterCount > 0 && (
              <span className="ml-1 rounded bg-accent px-1.5 text-xs text-accent-text">
                {activeFilterCount}
              </span>
            )}
          </button>
          {showFilters && (
            <div className="mt-2 flex flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
              <div>
                <label htmlFor="sc-buy">{t('scouting.teamBuy')}</label>
                <select id="sc-buy" value={buyType} onChange={(e) => setBuyType(e.target.value as BuyType | '')}>
                  <option value="">{t('scouting.anyFilter')}</option>
                  {BUY_TYPES.map((b) => (
                    <option key={b} value={b}>{t(`demos.buyTypes.${b}`)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="sc-opp-buy">{t('scouting.oppBuy')}</label>
                <select id="sc-opp-buy" value={oppBuyType} onChange={(e) => setOppBuyType(e.target.value as BuyType | '')}>
                  <option value="">{t('scouting.anyFilter')}</option>
                  {BUY_TYPES.map((b) => (
                    <option key={b} value={b}>{t(`demos.buyTypes.${b}`)}</option>
                  ))}
                </select>
              </div>
              <WeaponPicker
                idPrefix="sc-team-weapon"
                label={t('scouting.teamWeapon')}
                picks={teamWeapons}
                onChange={setTeamWeapons}
                addLabel={t('scouting.addWeapon')}
                countLabel={t('scouting.weaponCount')}
                removeLabel={t('scouting.removeWeapon')}
                hint={t('scouting.weaponMinHint')}
                catLabel={(c) => t(`scouting.weaponCategories.${c}`)}
              />
              <WeaponPicker
                idPrefix="sc-opp-weapon"
                label={t('scouting.oppWeapon')}
                picks={oppWeapons}
                onChange={setOppWeapons}
                addLabel={t('scouting.addWeapon')}
                countLabel={t('scouting.weaponCount')}
                removeLabel={t('scouting.removeWeapon')}
                hint={t('scouting.weaponMinHint')}
                catLabel={(c) => t(`scouting.weaponCategories.${c}`)}
              />
            </div>
          )}
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
          {ms?.trained && ms.timing_accuracy != null && (
            <span className="text-muted text-xs">
              {t('scouting.timingAccuracy')}: {pct(ms.timing_accuracy)}
              {ms.timing_baseline_accuracy != null && (
                <span className="text-muted"> ({pct(ms.timing_baseline_accuracy)})</span>
              )}
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
          {isAdmin && (
            <button className="border border-border bg-transparent text-text" onClick={() => evaluateMaps.mutate()} disabled={evaluateMaps.isPending}>
              {evaluateMaps.isPending ? t('common.loading') : t('scouting.testMaps')}
            </button>
          )}
        </div>
        {perMap && perMap.length > 0 && (
          <PerMapTable rows={perMap} maps={maps} tested={!!evaluateMaps.data} />
        )}
        {isAdmin && evaluateMaps.data && (!perMap || perMap.length === 0) && (
          <div className="text-muted mt-2 text-xs">{t('scouting.mapTestEmpty')}</div>
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="m-0">{t('scouting.placed')} ({tokens.length})</h2>
                <div className="flex flex-wrap gap-1.5">
                  <button className="border border-border bg-transparent text-text" onClick={() => fileRef.current?.click()}>{t('scouting.import')}</button>
                  {tokens.length > 0 && (
                    <button className="border border-border bg-transparent text-text" onClick={exportSetup}>{t('scouting.export')}</button>
                  )}
                  {tokens.length > 0 && (
                    <button className="border border-border bg-transparent text-text" onClick={() => setTokens([])}>{t('scouting.clear')}</button>
                  )}
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/json,.json"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) importSetup(f)
                    e.target.value = ''
                  }}
                />
              </div>
              {importErr && <p className="mt-1 mb-0 text-xs text-danger">{importErr}</p>}
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
              {teamIds.length > 1 && (
                <p className="mt-1.5 mb-0 text-xs text-muted">{t('scouting.multiTeamHint')}</p>
              )}
            </div>

            {result && <Prediction result={result} />}
          </div>
        </div>
      </div>

      {/* Historical tendencies + utility heatmap */}
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('scouting.tendencies')}{teamLabel ? ` · ${teamLabel}` : ''}</h2>
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
function PerMapTable({ rows, maps, tested }: { rows: PerMapMetric[]; maps?: MapOut[]; tested?: boolean }) {
  const { t } = useTranslation()
  const name = (id: string) => maps?.find((m) => m.id === id)?.name ?? id
  const cell = 'py-0.5 pr-2.5 pl-0 text-right whitespace-nowrap'
  const head = `${cell} border-b border-border font-semibold`
  return (
    <div className="mt-3 overflow-x-auto print:hidden">
      <div className="text-muted mb-1 text-xs">{tested ? t('scouting.mapTestResults') : t('scouting.byMap')}</div>
      <table className="border-collapse text-xs">
        <thead>
          <tr className="text-muted">
            <th className={`${head} text-left`}>{t('scouting.map')}</th>
            <th className={head}>{t('scouting.plants')}</th>
            <th className={head}>{t('scouting.okShort')}</th>
            <th className={head}>{t('scouting.siteAccShort')}</th>
            <th className={head}>{t('scouting.baselineShort')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.map_id}>
              <td className={`${cell} text-left`}>{name(r.map_id)}</td>
              <td className={cell}>{r.n_plant}</td>
              <td className={`${cell} font-semibold`}>{r.accuracy != null ? pct(r.accuracy) : '—'}</td>
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

      {result.timing && result.predicted_timing && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="mt-0 mb-2 text-sm">
            {t('scouting.executionTiming')}:{' '}
            <strong style={{ color: TIMING_COLOR[result.predicted_timing] ?? 'var(--color-text)' }}>
              {t(`scouting.timings.${result.predicted_timing}`)}
            </strong>{' '}
            {result.timing_confidence != null && (
              <span className="text-muted">({(result.timing_confidence * 100).toFixed(0)}%)</span>
            )}
          </p>
          {TIMING_ORDER.map((tm) => {
            const prob = result.timing?.find((x) => x.timing === tm)?.prob ?? 0
            return (
              <div key={tm} className="mb-2.5">
                <div className="flex justify-between text-sm">
                  <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">
                    {t(`scouting.timings.${tm}`)}
                  </span>
                  <span>{(prob * 100).toFixed(0)}%</span>
                </div>
                <div className="mt-0.5 h-3.5 rounded bg-[#1f2937]">
                  <div
                    className="h-full rounded"
                    style={{ width: `${prob * 100}%`, background: TIMING_COLOR[tm], minWidth: prob > 0 ? 2 : 0 }}
                  />
                </div>
              </div>
            )
          })}
          <p className="mt-1.5 mb-0 text-xs text-muted">{t('scouting.timingHint')}</p>
        </div>
      )}
    </div>
  )
}

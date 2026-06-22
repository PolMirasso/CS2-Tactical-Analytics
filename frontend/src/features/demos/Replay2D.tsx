import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiUrl } from '@/lib/apiClient'
import type {
  MapCalibration,
  ReplayFrame,
  ReplayPlayer,
  ReplayRound,
  ReplayRoundMeta,
  UtilityType,
} from '@/types/api'
import { useReplayMeta, useReplayRound } from './hooks'

const RADAR = 1024 // awpy radar images and our SVG viewBox are 1024×1024
const SIDE_COLOR: Record<string, string> = { t: '#f3c244', ct: '#5b9cff' }
const UTIL_COLOR: Record<UtilityType, string> = {
  smoke: '#9aa3b2',
  flash: '#f3c244',
  molotov: '#ff7a45',
  he: '#ff5d5d',
}
const SPEEDS = [0.5, 1, 2, 4]
const C4_TIME = 40
const ROUND_TIME = 115

const fmtClock = (sec: number): string => {
  const s = Math.max(0, Math.ceil(sec))
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`
}

// Grenade post-landing effect: lifetime (s) and world-space radius.
const UTIL_DUR: Record<UtilityType, number> = { smoke: 18, molotov: 7, flash: 0.35, he: 0.45 }
const UTIL_RADIUS: Record<UtilityType, number> = { smoke: 144, molotov: 165, flash: 90, he: 100 }

// nadeMask bits (mirrors backend NADE_* constants) → label + colour.
const NADES: { bit: number; label: string; color: string }[] = [
  { bit: 1, label: 'Smoke', color: UTIL_COLOR.smoke },
  { bit: 2, label: 'Flash', color: UTIL_COLOR.flash },
  { bit: 4, label: 'HE', color: UTIL_COLOR.he },
  { bit: 8, label: 'Molotov', color: UTIL_COLOR.molotov },
  { bit: 16, label: 'Decoy', color: '#7bd88f' },
]

type Pos = [number, number, number, number, number] // x, y, yaw, hp, z
// [armor, money, weaponIdx, clipAmmo, reserveAmmo, nadeMask]
type Stat = number[]

const isDead = (p: Pos): boolean => p[3] <= 0 || (p[0] === 0 && p[1] === 0)

/** Drop demoparser2's ``weapon_`` prefix and underscores for display. */
function prettyWeapon(w: string | undefined): string {
  if (!w) return '—'
  return w.replace(/^weapon_/, '').replace(/_/g, ' ')
}

function lerpPlayer(a: Pos, b: Pos, f: number): Pos | null {
  if (isDead(a) && isDead(b)) return null
  if (isDead(b)) return a
  if (isDead(a)) return b
  const dyaw = (((b[2] - a[2] + 180) % 360) + 360) % 360 - 180
  return [
    a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f,
    a[2] + dyaw * f,
    a[3] + (b[3] - a[3]) * f,
    f < 0.5 ? a[4] : b[4], // z: snap to nearest sample, levels don't interpolate
  ]
}

/**
 * World→SVG-pixel projection: radar calibration when available, else a fit.
 * On two-level maps (nuke) a point whose world z is below `lower_level_max_units`
 * projects with the `lower` calibration, which the radar draws as a separate inset.
 */
function useProjection(
  round: ReplayRound,
  cal: MapCalibration | null,
  hasRadar: boolean,
): (x: number, y: number, z?: number) => [number, number] {
  return useMemo(() => {
    if (cal && hasRadar) {
      const lower = cal.lower
      const zMax = cal.lower_level_max_units
      return (x: number, y: number, z?: number) => {
        const c = lower && zMax != null && z != null && z < zMax ? lower : cal
        return [(x - c.pos_x) / c.scale, (c.pos_y - y) / c.scale]
      }
    }
    // Fallback: fit all world points into the viewBox (no radar background).
    const xs: number[] = []
    const ys: number[] = []
    for (const fr of round.frames) {
      for (const p of fr.pos as Pos[]) {
        if (isDead(p)) continue
        xs.push(p[0])
        ys.push(p[1])
      }
    }
    for (const u of round.utility) {
      xs.push(u.from[0], u.to[0])
      ys.push(u.from[1], u.to[1])
    }
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const pad = 60
    const span = Math.max(maxX - minX, maxY - minY) || 1
    return (x: number, y: number) => [
      pad + ((x - minX) / span) * (RADAR - 2 * pad),
      pad + ((maxY - y) / span) * (RADAR - 2 * pad),
    ]
  }, [round, cal, hasRadar])
}

function frameAt(frames: ReplayFrame[], time: number, sampleHz: number) {
  const idx = time * sampleHz
  const i0 = Math.max(0, Math.min(frames.length - 1, Math.floor(idx)))
  const i1 = Math.min(frames.length - 1, i0 + 1)
  return { a: frames[i0].pos as Pos[], b: frames[i1].pos as Pos[], f: idx - i0, i0 }
}

type RosterEntry = { idx: number; player: ReplayPlayer; number: number }

/** Split the roster into CT/T sides, numbering each side 1..5. */
function useTeams(round: ReplayRound): { ct: RosterEntry[]; t: RosterEntry[] } {
  return useMemo(() => {
    const ct: RosterEntry[] = []
    const t: RosterEntry[] = []
    round.players.forEach((player, idx) => {
      const bucket = player.side === 'ct' ? ct : t
      bucket.push({ idx, player, number: bucket.length + 1 })
    })
    return { ct, t }
  }, [round])
}

/** One team's scoreboard column: number, name, weapon, money, hp/armor. */
function TeamPanel({
  side,
  entries,
  statFrame,
  weapons,
}: {
  side: string
  entries: RosterEntry[]
  statFrame: ReplayFrame
  weapons: string[]
}) {
  const { t } = useTranslation()
  const color = SIDE_COLOR[side] ?? '#fff'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, width: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontWeight: 700,
          fontSize: 13,
          color,
          textTransform: 'uppercase',
          letterSpacing: 0.5,
        }}
      >
        <span
          style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: color }}
        />
        {side === 'ct' ? 'CT' : 'T'}
      </div>
      {entries.map((e) => {
        const pos = (statFrame.pos[e.idx] as Pos) ?? [0, 0, 0, 0, 0]
        const st = (statFrame.st?.[e.idx] as Stat) ?? [0, 0, 0, 0, 0, 0]
        const hp = Math.max(0, Math.round(pos[3]))
        const dead = hp <= 0
        const weapon = prettyWeapon(weapons?.[st[2]])
        const clip = st[3] ?? 0
        const reserve = st[4] ?? 0
        const nadeMask = st[5] ?? 0
        const held = NADES.filter((n) => (nadeMask & n.bit) !== 0)
        return (
          <div
            key={e.player.steamid}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 3,
              padding: '6px 8px',
              borderRadius: 6,
              border: '1px solid var(--border)',
              background: '#11141a',
              opacity: dead ? 0.45 : 1,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 20,
                  height: 20,
                  borderRadius: 4,
                  background: color,
                  color: '#11141a',
                  fontWeight: 700,
                  fontSize: 13,
                  flexShrink: 0,
                }}
              >
                {e.number}
              </span>
              <span
                style={{
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  textDecoration: dead ? 'line-through' : undefined,
                }}
                title={e.player.name}
              >
                {e.player.name}
              </span>
              <span className="muted" title={t('replay.money')} style={{ fontSize: 13 }}>
                ${st[1]}
              </span>
            </div>
            <div className="muted" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, gap: 6 }}>
              <span title={t('replay.weapon')} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {weapon}
              </span>
              {!dead && (clip > 0 || reserve > 0) && (
                <span title={t('replay.ammo')} style={{ flexShrink: 0 }}>
                  {clip}/{reserve}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <span className="muted" title={t('replay.hp')}>{hp}♥</span>
              <span className="muted" title={t('replay.armor')}>{st[0]}🛡</span>
              {/* Utility currently carried. */}
              <span style={{ display: 'flex', gap: 3, marginLeft: 'auto' }}>
                {held.map((n) => (
                  <span
                    key={n.bit}
                    title={n.label}
                    style={{
                      display: 'inline-block',
                      width: 9,
                      height: 9,
                      borderRadius: 2,
                      background: n.color,
                    }}
                  />
                ))}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ReplayStage({
  round,
  mapId,
  calibration,
  hasRadar,
  sampleHz,
  fullscreen,
  rounds,
  currentRound,
  onRound,
}: {
  round: ReplayRound
  mapId: string
  calibration: MapCalibration | null
  hasRadar: boolean
  sampleHz: number
  fullscreen?: boolean
  rounds: ReplayRoundMeta[]
  currentRound: number | null
  onRound: (n: number) => void
}) {
  const { t } = useTranslation()
  const duration = round.duration_s
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [picked, setPicked] = useState<{ name: string; cmd: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const project = useProjection(round, calibration, hasRadar)
  const teams = useTeams(round)
  // Death spot per player (last alive world position + time), for the "X" marker.
  const deaths = useMemo(() => {
    const out: (null | { t: number; x: number; y: number; z: number })[] = round.players.map(() => null)
    const lastAlive: (null | [number, number, number])[] = round.players.map(() => null)
    for (const fr of round.frames) {
      ;(fr.pos as Pos[]).forEach((p, k) => {
        if (!isDead(p)) lastAlive[k] = [p[0], p[1], p[4]]
        else if (out[k] == null && lastAlive[k]) {
          out[k] = { t: fr.t, x: lastAlive[k]![0], y: lastAlive[k]![1], z: lastAlive[k]![2] }
        }
      })
    }
    return out
  }, [round])
  // Shot times grouped per player (sorted), for the firing indicator.
  const firesByPlayer = useMemo(() => {
    const m = new Map<number, number[]>()
    for (const [k, ft] of round.fires ?? []) {
      const arr = m.get(k)
      if (arr) arr.push(ft)
      else m.set(k, [ft])
    }
    for (const arr of m.values()) arr.sort((x, y) => x - y)
    return m
  }, [round])
  const lastTs = useRef<number>(0)
  const barRef = useRef<HTMLDivElement>(null)

  const seekFromClientX = (clientX: number) => {
    const el = barRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = Math.max(0, Math.min(rect.width, clientX - rect.left))
    setPlaying(false)
    setTime((x / rect.width) * duration)
  }

  useEffect(() => {
    if (!playing) return
    let raf = 0
    lastTs.current = performance.now()
    const tick = (now: number) => {
      const dt = (now - lastTs.current) / 1000
      lastTs.current = now
      setTime((tt) => {
        const nt = tt + dt * speed
        if (nt >= duration) {
          setPlaying(false)
          return duration
        }
        return nt
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, duration])

  const togglePlay = () => {
    if (!playing && time >= duration) setTime(0)
    setPlaying((p) => !p)
  }

  if (round.frames.length === 0) return null

  const { a, b, f, i0 } = frameAt(round.frames, time, sampleHz)
  const statFrame = round.frames[i0] // discrete scoreboard stats (no interp)
  // World radius → pixel radius under the active projection.
  const projectR = (x: number, y: number, worldR: number, z?: number): number => {
    const [px] = project(x, y, z)
    const [qx] = project(x + worldR, y, z)
    return Math.abs(qx - px)
  }
  // A player is "firing" if they shot within a short window before the playhead.
  const FIRE_WINDOW = 0.18
  const firing = (k: number): boolean => {
    const arr = firesByPlayer.get(k)
    if (!arr) return false
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] > time) continue
      return time - arr[i] <= FIRE_WINDOW
    }
    return false
  }
  // Kill feed: kills in the last few seconds, newest first.
  const KILLFEED_WINDOW = 7
  // Guard `?? []`: artifacts parsed before kills/utility existed lack the field.
  const visibleKills = (round.kills ?? [])
    .filter((k) => time >= k.t && time - k.t < KILLFEED_WINDOW)
    .slice(-6)
    .reverse()

  return (
    <div>
      <div
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            position: 'relative',
            width: '100%',
            // Cap by available viewport height (not max-height, which would make
            // the box rectangular and misalign the radar img vs the SVG overlay).
            maxWidth: fullscreen ? 'min(1100px, calc(100vh - 250px))' : 1000,
            minWidth: 320,
            flex: '1 1 520px',
            aspectRatio: '1 / 1',
            border: '1px solid var(--border)',
            borderRadius: 8,
            overflow: 'hidden',
            background: '#11141a',
          }}
        >
          {hasRadar && (
            <img
              src={apiUrl(`/maps/${mapId}/radar.png`)}
              alt={mapId}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 0.85 }}
            />
          )}
          <svg
            viewBox={`0 0 ${RADAR} ${RADAR}`}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
          >
            {/* Utility: in-flight grenade, then a timed effect that fades out.
                No persistent line — it appears in real time and disappears. */}
            {round.utility.map((u, i) => {
              const c = UTIL_COLOR[u.type] ?? '#fff'
              const wp: [number, number, number][] =
                u.path && u.path.length > 1
                  ? u.path
                  : [
                      [u.from[0], u.from[1], u.z ?? 0],
                      [u.to[0], u.to[1], u.z ?? 0],
                    ]
              const seg: number[] = []
              let total = 0
              for (let k = 1; k < wp.length; k++) {
                const d = Math.hypot(wp[k][0] - wp[k - 1][0], wp[k][1] - wp[k - 1][1])
                seg.push(d)
                total += d
              }
              const flight = Math.min(2.2, Math.max(0.4, total / 1600))
              const landT = u.t + flight
              const dur = UTIL_DUR[u.type] ?? 1
              const linger = 1.2

              if (time < u.t || time >= landT + Math.max(dur, linger)) return null

              if (time < landT) {
                const target = Math.max(0, Math.min(1, (time - u.t) / flight)) * total
                let acc = 0
                let idx = 0
                let localT = 0
                for (; idx < seg.length; idx++) {
                  if (acc + seg[idx] >= target) {
                    localT = seg[idx] ? (target - acc) / seg[idx] : 0
                    break
                  }
                  acc += seg[idx]
                }
                if (idx >= seg.length) {
                  idx = Math.max(0, seg.length - 1)
                  localT = 1
                }
                const a = wp[idx]
                const b = wp[idx + 1] ?? a
                const [gx, gy] = project(
                  a[0] + (b[0] - a[0]) * localT,
                  a[1] + (b[1] - a[1]) * localT,
                  a[2] + (b[2] - a[2]) * localT,
                )
                const pts = wp.slice(0, idx + 1).map((q) => project(q[0], q[1], q[2]))
                pts.push([gx, gy])
                return (
                  <g key={`u${i}`}>
                    <polyline
                      points={pts.map((pp) => pp.join(',')).join(' ')}
                      fill="none"
                      stroke={c}
                      strokeWidth={2}
                      strokeOpacity={0.7}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                    <circle cx={gx} cy={gy} r={6} fill={c} stroke="#11141a" strokeWidth={1.5} />
                  </g>
                )
              }

              const trailA = Math.max(0, 0.7 * (1 - (time - landT) / linger))
              const trail =
                trailA > 0 ? (
                  <polyline
                    points={wp.map((q) => project(q[0], q[1], q[2]).join(',')).join(' ')}
                    fill="none"
                    stroke={c}
                    strokeWidth={2}
                    strokeOpacity={trailA}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ) : null

              // Landed effect: fade in (0.25s) and fade out (last 1s).
              const age = time - landT
              const fadeIn = Math.min(1, age / 0.25)
              const fadeOut = Math.min(1, (dur - age) / Math.min(1, dur))
              const alpha = Math.max(0, Math.min(fadeIn, fadeOut))
              const [cx, cy] = project(u.to[0], u.to[1], u.z)
              const pr = projectR(u.to[0], u.to[1], UTIL_RADIUS[u.type] ?? 100, u.z)

              if (u.type === 'smoke') {
                return (
                  <g key={`u${i}`}>
                    {trail}
                    <circle cx={cx} cy={cy} r={pr} fill="#c7ccd6" opacity={0.5 * alpha} />
                    <circle cx={cx} cy={cy} r={pr} fill="none" stroke="#e6e9ef" strokeWidth={2} opacity={0.7 * alpha} />
                  </g>
                )
              }
              if (u.type === 'molotov') {
                const flicker = 0.32 + 0.12 * Math.sin(time * 22)
                return (
                  <g key={`u${i}`}>
                    {trail}
                    <circle cx={cx} cy={cy} r={pr} fill="#ff7a45" opacity={flicker * alpha} />
                    <circle cx={cx} cy={cy} r={pr} fill="none" stroke="#ff5d2e" strokeWidth={2} opacity={0.8 * alpha} />
                  </g>
                )
              }
              // flash / he: a quick burst that expands and vanishes.
              const burst = pr * (0.5 + 0.5 * Math.min(1, age / 0.12))
              return (
                <g key={`u${i}`}>
                  {trail}
                  <circle cx={cx} cy={cy} r={burst} fill={c} opacity={0.6 * alpha} />
                </g>
              )
            })}

            {/* Players: live dot (with firing flash) or a death "X". */}
            {round.players.map((player, k) => {
              const color = SIDE_COLOR[player.side] ?? '#fff'
              const live = lerpPlayer(a[k], b[k], f)
              if (live) {
                const [px, py, yaw] = live
                const [cx, cy] = project(px, py, live[4])
                // Facing tick: yaw is degrees CCW from +X; screen Y is flipped.
                const rad = (yaw * Math.PI) / 180
                const dirX = Math.cos(rad)
                const dirY = -Math.sin(rad)
                const isFiring = firing(k)
                return (
                  <g key={player.steamid}>
                    {isFiring && (
                      <>
                        <circle cx={cx} cy={cy} r={21} fill="none" stroke="#ffe066" strokeWidth={2} opacity={0.7} />
                        <line
                          x1={cx}
                          y1={cy}
                          x2={cx + dirX * 42}
                          y2={cy + dirY * 42}
                          stroke="#fff3b0"
                          strokeWidth={5}
                          strokeLinecap="round"
                        />
                        <circle cx={cx + dirX * 42} cy={cy + dirY * 42} r={6} fill="#ffe066" />
                      </>
                    )}
                    <line x1={cx} y1={cy} x2={cx + dirX * 24} y2={cy + dirY * 24} stroke={color} strokeWidth={3} />
                    <circle
                      cx={cx}
                      cy={cy}
                      r={13}
                      fill={color}
                      stroke="#11141a"
                      strokeWidth={2}
                      style={{ cursor: 'pointer' }}
                      onClick={() => {
                        const cmd = `setpos ${px.toFixed(1)} ${py.toFixed(1)} ${live[4].toFixed(1)};setang 0 ${yaw.toFixed(1)} 0`
                        setPicked({ name: player.name, cmd })
                        setCopied(false)
                      }}
                    >
                      <title>{player.name}</title>
                    </circle>
                    {/* Player name below the dot (outlined for readability). */}
                    <text
                      x={cx}
                      y={cy + 26}
                      textAnchor="middle"
                      fontSize={15}
                      fontWeight={600}
                      fill="#fff"
                      stroke="#11141a"
                      strokeWidth={3}
                      paintOrder="stroke"
                      style={{ pointerEvents: 'none' }}
                    >
                      {player.name}
                    </text>
                  </g>
                )
              }
              const d = deaths[k]
              if (d && time >= d.t) {
                const [cx, cy] = project(d.x, d.y, d.z)
                const s = 9
                return (
                  <g key={player.steamid} opacity={0.85}>
                    <line x1={cx - s} y1={cy - s} x2={cx + s} y2={cy + s} stroke={color} strokeWidth={3} strokeLinecap="round" />
                    <line x1={cx - s} y1={cy + s} x2={cx + s} y2={cy - s} stroke={color} strokeWidth={3} strokeLinecap="round" />
                    <title>{player.name}</title>
                  </g>
                )
              }
              return null
            })}

            {/* Planted bomb (shown from the plant time onward). */}
            {round.bomb && time >= round.bomb.t && (() => {
              const b = round.bomb!
              const [bx, by] = project(b.x, b.y, b.z ?? undefined)
              return (
                <g>
                  <circle cx={bx} cy={by} r={16} fill="none" stroke="#ff5d5d" strokeWidth={2} opacity={0.6} />
                  <rect x={bx - 12} y={by - 9} width={24} height={18} rx={3} fill="#d6452b" stroke="#fff" strokeWidth={1.5} />
                  <text
                    x={bx}
                    y={by}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={11}
                    fontWeight={700}
                    fill="#fff"
                    style={{ pointerEvents: 'none' }}
                  >
                    C4
                  </text>
                </g>
              )
            })()}
          </svg>

          {(() => {
            const planted = round.bomb && time >= round.bomb.t
            const remaining = planted ? C4_TIME - (time - round.bomb!.t) : ROUND_TIME - time
            const danger = !!planted
            return (
              <div
                style={{
                  position: 'absolute',
                  top: 10,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '2px 16px',
                  borderRadius: 4,
                  background: 'rgba(13,16,22,0.9)',
                  border: `1px solid ${danger ? 'rgba(255,93,93,0.55)' : 'var(--border)'}`,
                  color: danger ? '#ff5d5d' : '#e6e9ef',
                  fontSize: 22,
                  fontWeight: 700,
                  letterSpacing: 1,
                  fontVariantNumeric: 'tabular-nums',
                  pointerEvents: 'none',
                }}
              >
                {danger && (
                  <span style={{ width: 9, height: 9, borderRadius: 2, background: '#ff5d5d' }} />
                )}
                {fmtClock(remaining)}
              </div>
            )
          })()}

          {picked && (
            <div
              style={{
                position: 'absolute',
                bottom: 8,
                left: 8,
                maxWidth: '75%',
                display: 'flex',
                flexDirection: 'column',
                gap: 5,
                padding: '8px 10px',
                borderRadius: 6,
                background: 'rgba(10,12,16,0.92)',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <strong style={{ fontSize: 12 }}>{picked.name}</strong>
                <button className="ghost" style={{ padding: '0 6px' }} onClick={() => setPicked(null)}>
                  ✕
                </button>
              </div>
              <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{picked.cmd}</code>
              <button
                style={{ padding: '3px 8px', alignSelf: 'flex-start' }}
                onClick={async () => {
                  await navigator.clipboard.writeText(picked.cmd)
                  setCopied(true)
                }}
              >
                {copied ? t('replay.copied') : t('replay.copyCmd')}
              </button>
            </div>
          )}

          {/* Kill feed (top-right): attacker — weapon [HS] → victim. */}
          {visibleKills.length > 0 && (
            <div
              style={{
                position: 'absolute',
                top: 8,
                right: 8,
                display: 'flex',
                flexDirection: 'column',
                gap: 4,
                alignItems: 'flex-end',
                pointerEvents: 'none',
              }}
            >
              {visibleKills.map((k, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    background: 'rgba(10,12,16,0.82)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '3px 8px',
                    fontSize: 13,
                    whiteSpace: 'nowrap',
                  }}
                >
                  <span style={{ color: SIDE_COLOR[k.as] ?? '#fff', fontWeight: 600 }}>{k.atk}</span>
                  <span className="muted">{prettyWeapon(k.wp)}</span>
                  {k.hs && (
                    <span title="headshot" style={{ color: '#ff5d5d', fontWeight: 700 }}>
                      HS
                    </span>
                  )}
                  <span style={{ color: '#7a8190' }}>→</span>
                  <span style={{ color: SIDE_COLOR[k.vs] ?? '#fff', fontWeight: 600 }}>{k.vic}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Both teams stacked in a narrow column to the right of the map. */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            flex: '0 1 240px',
            minWidth: 200,
            maxWidth: 260,
          }}
        >
          <TeamPanel side="ct" entries={teams.ct} statFrame={statFrame} weapons={round.weapons} />
          <TeamPanel side="t" entries={teams.t} statFrame={statFrame} weapons={round.weapons} />
        </div>
      </div>

      {!hasRadar && <p className="muted" style={{ marginTop: 8 }}>{t('replay.noRadar')}</p>}

      {/* Round strip: winner colour on top, clickable round number below. */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 14 }}>
        {rounds.map((r) => {
          const active = r.round_number === currentRound
          const wc = r.winner === 'ct' ? SIDE_COLOR.ct : r.winner === 't' ? SIDE_COLOR.t : 'transparent'
          return (
            <button
              key={r.round_number}
              onClick={() => onRound(r.round_number)}
              title={`${t('replay.round')} ${r.round_number}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                padding: 0,
                minWidth: 30,
                overflow: 'hidden',
                borderRadius: 5,
                cursor: 'pointer',
                border: `1px solid ${active ? 'var(--text)' : 'var(--border)'}`,
                background: active ? 'var(--surface-2)' : '#11141a',
              }}
            >
              <span style={{ height: 4, background: wc }} />
              <span
                style={{
                  padding: '4px 7px',
                  fontSize: 12,
                  fontWeight: active ? 700 : 400,
                  color: active ? 'var(--text)' : 'var(--muted)',
                }}
              >
                {r.round_number}
              </span>
            </button>
          )
        })}
      </div>

      {/* Round timeline: drag/click to seek; markers for utility and kills. */}
      <div
        ref={barRef}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          seekFromClientX(e.clientX)
        }}
        onPointerMove={(e) => {
          if (e.buttons & 1) seekFromClientX(e.clientX)
        }}
        style={{
          position: 'relative',
          height: 30,
          marginTop: 10,
          background: '#11141a',
          border: '1px solid var(--border)',
          borderRadius: 6,
          cursor: 'pointer',
          touchAction: 'none',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: 0,
            width: `${(time / duration) * 100}%`,
            background: 'rgba(79,140,255,0.18)',
          }}
        />
        {round.utility.map((u, i) => (
          <span
            key={`m${i}`}
            title={`${u.type} · ${u.t.toFixed(1)}s`}
            style={{
              position: 'absolute',
              top: 5,
              left: `${(u.t / duration) * 100}%`,
              transform: 'translateX(-50%)',
              width: 9,
              height: 9,
              borderRadius: '50%',
              background: UTIL_COLOR[u.type] ?? '#fff',
              pointerEvents: 'none',
            }}
          />
        ))}
        {(round.kills ?? []).map((k, i) => (
          <span
            key={`k${i}`}
            title={`${k.atk} → ${k.vic}`}
            style={{
              position: 'absolute',
              bottom: 4,
              left: `${(k.t / duration) * 100}%`,
              transform: 'translateX(-50%)',
              width: 0,
              height: 0,
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderTop: `7px solid ${SIDE_COLOR[k.as] ?? '#fff'}`,
              pointerEvents: 'none',
            }}
          />
        ))}
        <div
          style={{
            position: 'absolute',
            top: -2,
            bottom: -2,
            left: `${(time / duration) * 100}%`,
            width: 2,
            background: 'var(--text)',
            pointerEvents: 'none',
          }}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
        <button className="ghost" onClick={togglePlay} style={{ minWidth: 110 }}>
          {playing ? t('replay.pause') : t('replay.play')}
        </button>
        <span className="muted" style={{ minWidth: 96 }}>
          {time.toFixed(1)}s / {duration.toFixed(1)}s
        </span>
        <span className="muted" style={{ marginLeft: 8 }}>{t('replay.speed')}:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            className="badge"
            onClick={() => setSpeed(s)}
            style={{
              cursor: 'pointer',
              borderColor: speed === s ? 'var(--text)' : 'var(--border)',
              color: speed === s ? 'var(--text)' : undefined,
            }}
          >
            {s}×
          </button>
        ))}
      </div>
    </div>
  )
}

export function Replay2D({ demoId, fullscreen }: { demoId: number; fullscreen?: boolean }) {
  const { t } = useTranslation()
  const meta = useReplayMeta(demoId)
  const [round, setRound] = useState<number | null>(null)

  useEffect(() => {
    if (round == null && meta.data && meta.data.rounds.length > 0) {
      setRound(meta.data.rounds[0].round_number)
    }
  }, [meta.data, round])

  const roundQ = useReplayRound(demoId, round)

  if (meta.isLoading) return <p className="muted">{t('common.loading')}</p>
  if (meta.isError || !meta.data) {
    return (
      <div className="card">
        <h2>{t('replay.title')}</h2>
        <p className="muted">{t('replay.noReplay')}</p>
      </div>
    )
  }

  const replayMeta = meta.data

  return (
    <div className="card">
      <h2>{t('replay.title')}</h2>
      {roundQ.data ? (
        <ReplayStage
          key={round ?? 0}
          round={roundQ.data}
          mapId={replayMeta.map_id}
          calibration={replayMeta.calibration}
          hasRadar={replayMeta.has_radar}
          sampleHz={replayMeta.sample_hz}
          fullscreen={fullscreen}
          rounds={replayMeta.rounds}
          currentRound={round}
          onRound={setRound}
        />
      ) : (
        <p className="muted">{t('common.loading')}</p>
      )}
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiUrl } from '@/lib/apiClient'
import type {
  MapCalibration,
  ReplayFrame,
  ReplayRound,
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

type Pos = [number, number, number, number] // x, y, yaw, hp

const isDead = (p: Pos): boolean => p[3] <= 0 || (p[0] === 0 && p[1] === 0)

function lerpPlayer(a: Pos, b: Pos, f: number): Pos | null {
  if (isDead(a) && isDead(b)) return null
  if (isDead(b)) return a
  if (isDead(a)) return b
  return [
    a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f,
    a[2] + (b[2] - a[2]) * f,
    a[3] + (b[3] - a[3]) * f,
  ]
}

/** World→SVG-pixel projection: radar calibration when available, else a fit. */
function useProjection(
  round: ReplayRound,
  cal: MapCalibration | null,
  hasRadar: boolean,
): (x: number, y: number) => [number, number] {
  return useMemo(() => {
    if (cal && hasRadar) {
      return (x: number, y: number) => [(x - cal.pos_x) / cal.scale, (cal.pos_y - y) / cal.scale]
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
  return { a: frames[i0].pos as Pos[], b: frames[i1].pos as Pos[], f: idx - i0 }
}

function ReplayStage({
  round,
  mapId,
  calibration,
  hasRadar,
  sampleHz,
}: {
  round: ReplayRound
  mapId: string
  calibration: MapCalibration | null
  hasRadar: boolean
  sampleHz: number
}) {
  const { t } = useTranslation()
  const duration = round.duration_s
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const project = useProjection(round, calibration, hasRadar)
  const lastTs = useRef<number>(0)

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

  const { a, b, f } = frameAt(round.frames, time, sampleHz)
  const players = round.players.map((p, k) => {
    // Frames are aligned to the roster, so a[k]/b[k] always exist.
    const pos = lerpPlayer(a[k], b[k], f)
    return pos ? { player: p, pos } : null
  })
  const shotsThrown = round.utility.filter((u) => u.t <= time)

  return (
    <div>
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 680,
          margin: '0 auto',
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
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.85 }}
          />
        )}
        <svg
          viewBox={`0 0 ${RADAR} ${RADAR}`}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        >
          {/* Utility throw→land lines (only those already thrown). */}
          {shotsThrown.map((u, i) => {
            const [fx, fy] = project(u.from[0], u.from[1])
            const [tx, ty] = project(u.to[0], u.to[1])
            const c = UTIL_COLOR[u.type] ?? '#fff'
            return (
              <g key={`u${i}`}>
                <line
                  x1={fx}
                  y1={fy}
                  x2={tx}
                  y2={ty}
                  stroke={c}
                  strokeWidth={3}
                  strokeDasharray="10 8"
                  opacity={0.85}
                />
                <circle cx={tx} cy={ty} r={10} fill={c} opacity={0.5} />
                <circle cx={tx} cy={ty} r={10} fill="none" stroke={c} strokeWidth={2} />
              </g>
            )
          })}

          {/* Players */}
          {players.map((entry, k) => {
            if (!entry) return null
            const [px, py, yaw] = entry.pos
            const [cx, cy] = project(px, py)
            const color = SIDE_COLOR[entry.player.side] ?? '#fff'
            // Facing tick: yaw is degrees CCW from +X; screen Y is flipped.
            const rad = (yaw * Math.PI) / 180
            const fx = cx + Math.cos(rad) * 22
            const fy = cy - Math.sin(rad) * 22
            return (
              <g key={entry.player.steamid}>
                <line x1={cx} y1={cy} x2={fx} y2={fy} stroke={color} strokeWidth={3} />
                <circle cx={cx} cy={cy} r={13} fill={color} stroke="#11141a" strokeWidth={2}>
                  <title>{entry.player.name}</title>
                </circle>
              </g>
            )
          })}
        </svg>
      </div>

      {!hasRadar && <p className="muted" style={{ marginTop: 8 }}>{t('replay.noRadar')}</p>}

      {/* Controls */}
      <div className="row" style={{ marginTop: 12, alignItems: 'center', gap: 12 }}>
        <button className="ghost" onClick={togglePlay} style={{ minWidth: 110 }}>
          {playing ? t('replay.pause') : t('replay.play')}
        </button>
        <input
          type="range"
          min={0}
          max={duration}
          step={0.1}
          value={time}
          onChange={(e) => {
            setPlaying(false)
            setTime(Number(e.target.value))
          }}
          style={{ flex: 1 }}
        />
        <span className="muted" style={{ minWidth: 96, textAlign: 'right' }}>
          {time.toFixed(1)}s / {duration.toFixed(1)}s
        </span>
      </div>

      <div className="row" style={{ marginTop: 8, alignItems: 'center', gap: 6 }}>
        <span className="muted">{t('replay.speed')}:</span>
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

      {/* Utility timeline */}
      <p className="muted" style={{ marginTop: 16, marginBottom: 6 }}>
        {t('replay.utilityTimeline')}
      </p>
      <div
        style={{
          position: 'relative',
          height: 22,
          background: '#11141a',
          border: '1px solid var(--border)',
          borderRadius: 6,
        }}
      >
        {/* playhead */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: `${(time / duration) * 100}%`,
            width: 2,
            background: 'var(--text)',
          }}
        />
        {round.utility.map((u, i) => (
          <button
            key={`m${i}`}
            title={`${u.type} / ${u.t.toFixed(1)}s`}
            onClick={() => {
              setPlaying(false)
              setTime(u.t)
            }}
            style={{
              position: 'absolute',
              top: 3,
              left: `${(u.t / duration) * 100}%`,
              transform: 'translateX(-50%)',
              width: 12,
              height: 12,
              padding: 0,
              borderRadius: '50%',
              border: '1px solid #11141a',
              background: UTIL_COLOR[u.type] ?? '#fff',
              cursor: 'pointer',
            }}
          />
        ))}
      </div>
    </div>
  )
}

export function Replay2D({ demoId }: { demoId: number }) {
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

  // Local binding so the narrowing survives inside nested closures below.
  const replayMeta = meta.data

  return (
    <div className="card">
      <h2>{t('replay.title')}</h2>
      <div className="row" style={{ alignItems: 'center', gap: 8, maxWidth: 280 }}>
        <span className="muted">{t('replay.round')}:</span>
        <select
          value={round ?? ''}
          onChange={(e) => setRound(Number(e.target.value))}
          style={{ flex: 1 }}
        >
          {replayMeta.rounds.map((r) => (
            <option key={r.round_number} value={r.round_number}>
              {r.round_number}
            </option>
          ))}
        </select>
      </div>

      <div style={{ marginTop: 12 }}>
        {roundQ.data ? (
          <ReplayStage
            key={round ?? 0}
            round={roundQ.data}
            mapId={replayMeta.map_id}
            calibration={replayMeta.calibration}
            hasRadar={replayMeta.has_radar}
            sampleHz={replayMeta.sample_hz}
          />
        ) : (
          <p className="muted">{t('common.loading')}</p>
        )}
      </div>
    </div>
  )
}

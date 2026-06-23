import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlayerStatOut, RoundOut } from '@/types/api'

const pct = (wins: number, total: number) => (total ? Math.round((wins / total) * 100) : 0)

function groupByTeam(players: PlayerStatOut[]): [string, PlayerStatOut[]][] {
  const groups = new Map<string, PlayerStatOut[]>()
  for (const p of players) {
    const key = p.team ?? '—'
    ;(groups.get(key) ?? groups.set(key, []).get(key)!).push(p)
  }
  return [...groups.entries()]
}

export function PlayerScoreboard({ players }: { players: PlayerStatOut[] }) {
  const { t } = useTranslation()
  if (players.length === 0) return null
  return (
    <div className="card">
      <h2>{t('stats.scoreboard', 'Estadísticas de jugadores')}</h2>
      <table>
        <thead>
          <tr>
            <th>{t('stats.player', 'Jugador')}</th>
            <th>K</th>
            <th>D</th>
            <th>A</th>
            <th>+/-</th>
            <th>HS%</th>
            <th>ADR</th>
          </tr>
        </thead>
        <tbody>
          {groupByTeam(players).map(([team, group]) => (
            <Fragment key={team}>
              <tr>
                <th colSpan={7} style={{ textAlign: 'left', color: '#9aa3b2', paddingTop: 12 }}>
                  {team}
                </th>
              </tr>
              {group.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>{p.kills}</td>
                  <td>{p.deaths}</td>
                  <td>{p.assists}</td>
                  <td style={{ color: p.kills - p.deaths >= 0 ? '#7bd88f' : '#ff5d5d' }}>
                    {p.kills - p.deaths > 0 ? '+' : ''}
                    {p.kills - p.deaths}
                  </td>
                  <td>{p.kills ? Math.round((p.headshots / p.kills) * 100) : 0}%</td>
                  <td>{p.adr != null ? p.adr.toFixed(1) : '-'}</td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface Tally {
  wins: number
  total: number
}

function tally(rounds: RoundOut[], key: (r: RoundOut) => string): Record<string, Tally> {
  const out: Record<string, Tally> = {}
  for (const r of rounds) {
    if (!r.winner) continue
    const k = key(r)
    const cell = (out[k] ??= { wins: 0, total: 0 })
    cell.total += 1
    if (r.winner === 't') cell.wins += 1 // rounds are recorded from the T side
  }
  return out
}

function Bar({ label, cell }: { label: string; cell: Tally }) {
  const p = pct(cell.wins, cell.total)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 70px', gap: 8, alignItems: 'center' }}>
      <span className="muted" style={{ fontSize: 13 }}>{label}</span>
      <div style={{ height: 14, borderRadius: 7, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
        <div style={{ width: `${p}%`, height: '100%', background: 'var(--accent, #4f8cff)' }} />
      </div>
      <span style={{ fontSize: 13 }}>
        {p}% <span className="muted">({cell.wins}/{cell.total})</span>
      </span>
    </div>
  )
}

export function WinRateSummary({ rounds }: { rounds: RoundOut[] }) {
  const { t } = useTranslation()
  const withOutcome = rounds.filter((r) => r.winner)
  if (withOutcome.length === 0) return null

  const tWins = withOutcome.filter((r) => r.winner === 't').length
  const total = withOutcome.length
  const byBuy = tally(withOutcome, (r) => r.buy_type)
  const bySite = tally(withOutcome, (r) => r.target_site)

  // Pistol conversion: of pistols won, how many were followed by another win.
  const byNumber = new Map(rounds.map((r) => [r.round_number, r]))
  let pistolWon = 0
  let converted = 0
  for (const r of withOutcome) {
    if (r.buy_type !== 'pistol' || r.winner !== 't') continue
    pistolWon += 1
    const next = byNumber.get(r.round_number + 1)
    if (next?.winner === 't') converted += 1
  }

  return (
    <div className="card">
      <h2>{t('stats.winRate', 'Win rate (lado T)')}</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        T {pct(tWins, total)}% · CT {pct(total - tWins, total)}%
        {pistolWon > 0 && (
          <span style={{ marginLeft: 12 }}>
            · {t('stats.pistolConversion', 'Conversión pistola')}: {pct(converted, pistolWon)}%
          </span>
        )}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {Object.entries(byBuy).map(([k, cell]) => (
          <Bar key={k} label={t(`demos.buyTypes.${k}`, k)} cell={cell} />
        ))}
      </div>
      <h3 style={{ marginBottom: 6 }}>{t('demos.site')}</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {Object.entries(bySite).map(([k, cell]) => (
          <Bar key={k} label={k} cell={cell} />
        ))}
      </div>
    </div>
  )
}

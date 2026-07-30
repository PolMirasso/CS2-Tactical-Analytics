import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { formatDate, formatDay } from '@/lib/format'
import type { PlayerHit, PlayerProfile } from '@/types/api'
import { usePlayerProfile, usePlayerSearch, useRefreshPlayer } from './hooks'

const CARD = 'mb-5 rounded-[10px] border border-border bg-surface p-4'
const HLTV = 'https://www.hltv.org'

function PlayerSearch({
  collapsed,
  onSelect,
}: {
  collapsed: boolean
  onSelect: (p: PlayerHit) => void
}) {
  const { t } = useTranslation()
  const [term, setTerm] = useState('')
  const [open, setOpen] = useState(false)
  const { data, isFetching } = usePlayerSearch(term)

  const select = (p: PlayerHit) => {
    setTerm('')
    setOpen(false)
    onSelect(p)
  }

  if (collapsed && !open) {
    return (
      <button
        className="mb-5 w-full rounded-[10px] border border-border bg-surface px-4 py-2 text-left text-muted"
        onClick={() => setOpen(true)}
      >
        {t('players.searchAnother')}
      </button>
    )
  }

  return (
    <div className={CARD}>
      <label htmlFor="player-search">{t('players.search')}</label>
      <input
        id="player-search"
        value={term}
        autoFocus={collapsed}
        placeholder={t('players.searchPlaceholder')}
        onChange={(e) => setTerm(e.target.value)}
      />
      {isFetching && <p className="text-muted">{t('common.loading')}</p>}
      {data && data.length === 0 && <p className="text-muted">{t('common.noResults')}</p>}
      {data && data.length > 0 && (
        <table>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <td className="w-9">
                  {p.image && <img src={p.image} alt="" className="h-8 w-8 rounded-full object-cover" />}
                </td>
                <td>
                  <button
                    className="border-0 bg-transparent p-0 font-semibold text-accent"
                    onClick={() => select(p)}
                  >
                    {p.nick}
                  </button>
                  {p.name && <span className="text-muted"> · {p.name}</span>}
                </td>
                <td className="text-muted">{p.team_name ?? '-'}</td>
                <td className="text-right text-muted">
                  {p.retired ? t('players.retired') : p.country ?? ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function StatGrid({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
      {items.map((s) => (
        <div key={s.label} className="rounded-lg border border-border bg-surface-2 p-3 text-center">
          <div className="text-xl font-bold">{s.value}</div>
          <div className="text-xs text-muted">{s.label}</div>
        </div>
      ))}
    </div>
  )
}

function RoleBars({ roles }: { roles: PlayerProfile['roles'] }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-2">
      {roles.map((r) => (
        <div key={r.role}>
          <div className="flex justify-between text-sm">
            <span>{t(`players.roles.${r.role}`, r.role)}</span>
            <span className="text-muted">{r.score}/100</span>
          </div>
          <div className="mt-0.5 h-3.5 rounded bg-[#1f2937]">
            <div
              className="h-full rounded bg-accent"
              style={{ width: `${r.score}%`, minWidth: r.score ? 2 : 0 }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function Profile({ profile }: { profile: PlayerProfile }) {
  const { t } = useTranslation()
  const refresh = useRefreshPlayer()

  const subtitle = [
    profile.name,
    profile.country,
    profile.team_name,
    profile.age ? t('players.years', { n: profile.age }) : null,
    profile.role,
  ].filter(Boolean)

  return (
    <>
      <div className={CARD}>
        <div className="flex flex-wrap items-center gap-4">
          {profile.image && (
            <img src={profile.image} alt="" className="h-20 w-20 rounded-lg object-cover" />
          )}
          <div className="flex-1">
            <h2 className="mb-0">{profile.nick}</h2>
            <p className="text-muted">{subtitle.join(' · ')}</p>
            <a href={`${HLTV}/player/${profile.id}/-`} target="_blank" rel="noreferrer">
              {t('players.viewOnHltv')}
            </a>
          </div>
          {profile.rating && (
            <div className="text-center">
              <div className="text-3xl font-bold">{profile.rating}</div>
              <div className="text-xs text-muted">{profile.rating_label}</div>
              {profile.rating_note && (
                <div className="mt-1 text-xs text-muted">{profile.rating_note}</div>
              )}
            </div>
          )}
        </div>
        {profile.stats_window && (
          <p className="mt-3 text-xs text-muted">
            {t('players.statsWindow', { window: profile.stats_window })}
          </p>
        )}
        <p className="mt-1 text-xs text-muted">
          {t('players.updated', { when: formatDate(profile.fetched_at) })}{' '}
          <button
            className="ml-2 border border-border bg-transparent text-text"
            onClick={() => refresh.mutate(profile.id)}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? t('common.loading') : t('players.refresh')}
          </button>
        </p>
      </div>

      {profile.summary.length > 0 && (
        <div className={CARD}>
          <h2>{t('players.summary')}</h2>
          <StatGrid items={profile.summary} />
        </div>
      )}

      {profile.roles.length > 0 && (
        <div className={CARD}>
          <h2>{t('players.rolesTitle')}</h2>
          <p className="text-muted">{t('players.rolesHint')}</p>
          <RoleBars roles={profile.roles} />
        </div>
      )}

      {profile.matches.length > 0 && (
        <div className={CARD}>
          <h2>{t('players.matches')}</h2>
          <table>
            <thead>
              <tr>
                <th>{t('players.date')}</th>
                <th>{t('players.event')}</th>
                <th>{t('demos.opponent')}</th>
                <th className="text-right">{t('players.score')}</th>
              </tr>
            </thead>
            <tbody>
              {profile.matches.map((m, i) => (
                <tr key={`${m.url ?? i}`}>
                  <td className="text-muted">{formatDay(m.match_date)}</td>
                  <td className="text-muted">{m.event ?? '-'}</td>
                  <td>
                    {m.url ? (
                      <a href={`${HLTV}${m.url}`} target="_blank" rel="noreferrer">
                        {m.opponent ?? '-'}
                      </a>
                    ) : (
                      m.opponent ?? '-'
                    )}
                  </td>
                  <td
                    className={`text-right ${
                      m.won === null ? '' : m.won ? 'text-ok' : 'text-danger'
                    }`}
                  >
                    {m.score ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {profile.teams.length > 0 && (
        <div className={CARD}>
          <h2>{t('players.teams')}</h2>
          <table>
            <thead>
              <tr>
                <th>{t('players.team')}</th>
                <th>{t('players.from')}</th>
                <th>{t('players.to')}</th>
              </tr>
            </thead>
            <tbody>
              {profile.teams.map((s, i) => (
                <tr key={`${s.team_id ?? s.team_name}-${i}`}>
                  <td>
                    {s.team_id ? (
                      <a href={`${HLTV}/team/${s.team_id}/-`} target="_blank" rel="noreferrer">
                        {s.team_name}
                      </a>
                    ) : (
                      s.team_name
                    )}
                  </td>
                  <td className="text-muted">{formatDay(s.start)}</td>
                  <td className="text-muted">{s.end ? formatDay(s.end) : t('players.present')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export function PlayersPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { id } = useParams()
  const { data: profile, isLoading, isError, error } = usePlayerProfile(id)

  return (
    <div>
      <h1>{t('players.title')}</h1>
      <p className="text-muted">{t('players.subtitle')}</p>

      <PlayerSearch collapsed={Boolean(id)} onSelect={(p) => navigate(`/players/${p.id}`)} />

      {isLoading && (
        <div className={CARD}>
          <p className="text-muted">{t('common.loading')}</p>
          <p className="text-sm text-muted">{t('players.slowHint')}</p>
        </div>
      )}
      {isError && (
        <p className="my-2 text-[0.9rem] text-danger">
          {(error as Error)?.message || t('common.error')}
        </p>
      )}
      {profile && <Profile profile={profile} />}
    </div>
  )
}

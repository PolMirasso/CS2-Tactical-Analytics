import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from '@/features/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/format'
import type { DateRange, DownloadJobOut, TeamHit, Visibility } from '@/types/api'
import { TeamSearch } from './TeamSearch'
import { useDownloadJobs, useStartDownload } from './hooks'

// Overall progress: matches are the stable unit (a job has a fixed match total,
// but its demo total only grows as each match archive is downloaded).
function jobProgress(job: DownloadJobOut): number {
  if (job.status === 'completed') return 100
  if (job.status === 'failed' || job.matches_total === 0) return 0
  return Math.round((job.matches / job.matches_total) * 100)
}

const DATE_RANGES: DateRange[] = [
  'last_month',
  'last_3_months',
  'last_6_months',
  'last_12_months',
]

export function HltvPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [team, setTeam] = useState<TeamHit | null>(null)
  const [dateRange, setDateRange] = useState<DateRange>('last_3_months')
  const [visibility, setVisibility] = useState<Visibility>('public')
  const [maxMatches, setMaxMatches] = useState(100)
  const [error, setError] = useState<string | null>(null)

  const start = useStartDownload()
  const { data: jobs } = useDownloadJobs()
  const [openJobs, setOpenJobs] = useState<Record<string, boolean>>({})
  const toggleJob = (id: string) =>
    setOpenJobs((o) => ({ ...o, [id]: !o[id] }))

  async function onStart() {
    if (!team) return
    setError(null)
    try {
      await start.mutateAsync({
        team_id: team.id,
        team_name: team.name,
        date_range: dateRange,
        visibility,
        max_matches: maxMatches,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    }
  }

  return (
    <div>
      <h1>{t('hltv.title')}</h1>

      {!isAdmin && <p className="error">{t('hltv.adminOnly')}</p>}

      <div className="card" style={{ opacity: isAdmin ? 1 : 0.5 }}>
        <TeamSearch onSelect={setTeam} />

        {team && (
          <>
            <p>
              {t('hltv.selectTeam')}: <strong>{team.name}</strong> (#{team.id})
            </p>
            <div className="row" style={{ maxWidth: 520 }}>
              <div>
                <label htmlFor="range">{t('hltv.dateRange')}</label>
                <select
                  id="range"
                  value={dateRange}
                  onChange={(e) => setDateRange(e.target.value as DateRange)}
                >
                  {DATE_RANGES.map((r) => (
                    <option key={r} value={r}>
                      {t(`hltv.range.${r}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="vis">{t('demos.visibility')}</label>
                <select
                  id="vis"
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value as Visibility)}
                >
                  <option value="public">public</option>
                  <option value="private">private</option>
                </select>
              </div>
              <div>
                <label htmlFor="maxm">{t('hltv.maxMatches')}</label>
                <input
                  id="maxm"
                  type="number"
                  min={1}
                  max={200}
                  value={maxMatches}
                  onChange={(e) => setMaxMatches(Math.max(1, Math.min(200, +e.target.value || 1)))}
                />
              </div>
            </div>
            <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>{t('hltv.maxMatchesHint')}</p>
            {error && <p className="error">{error}</p>}
            <button onClick={onStart} disabled={!isAdmin || start.isPending}>
              {t('hltv.startDownload')}
            </button>
          </>
        )}
      </div>

      <div className="card">
        <h2>{t('hltv.jobs')}</h2>
        {!jobs || jobs.length === 0 ? (
          <p className="muted">{t('hltv.noJobs')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 24 }}></th>
                <th>{t('demos.team')}</th>
                <th>{t('demos.status')}</th>
                <th>{t('hltv.matches')}</th>
                <th>{t('hltv.ingested')}</th>
                <th>{t('demos.created')}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const open = !!openJobs[job.id]
                return (
                  <Fragment key={job.id}>
                    <tr
                      onClick={() => toggleJob(job.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="muted" style={{ textAlign: 'center' }}>
                        {open ? '▾' : '▸'}
                      </td>
                      <td>{job.team_name ?? job.team_id}</td>
                      <td>
                        <StatusBadge status={job.status} />
                        {job.error && <div className="error">{job.error}</div>}
                        {job.status === 'completed' &&
                          job.matches_total === 0 &&
                          job.demos_ingested === 0 && (
                            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                              {t(
                                'hltv.noMatches',
                                'Sin partidos en este periodo (el equipo puede estar inactivo o haber cambiado de nombre).',
                              )}
                            </div>
                          )}
                      </td>
                      <td>
                        {job.matches_total ? `${job.matches}/${job.matches_total}` : job.matches}
                      </td>
                      <td>
                        {job.demos_total
                          ? `${job.demos_ingested}/${job.demos_total}`
                          : job.demos_ingested}
                      </td>
                      <td className="muted">{formatDate(job.created_at)}</td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={6} style={{ background: 'rgba(255,255,255,0.02)' }}>
                          <JobDetails job={job} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div
      style={{
        position: 'relative',
        height: 18,
        borderRadius: 9,
        background: 'rgba(255,255,255,0.08)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          background: 'var(--accent, #4f8cff)',
          transition: 'width 0.3s ease',
        }}
      />
      <span
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {pct}%
      </span>
    </div>
  )
}

function JobDetails({ job }: { job: DownloadJobOut }) {
  const { t } = useTranslation()
  const rows: [string, string][] = [
    [t('hltv.matches'), job.matches_total ? `${job.matches} / ${job.matches_total}` : `${job.matches}`],
    [t('hltv.demos'), job.demos_total ? `${job.demos_ingested} / ${job.demos_total}` : `${job.demos_ingested}`],
    [t('hltv.dateRange'), t(`hltv.range.${job.date_range}`, job.date_range)],
    [t('demos.visibility'), job.visibility],
    [t('demos.created'), formatDate(job.created_at)],
    [t('hltv.updated'), formatDate(job.updated_at)],
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '8px 4px' }}>
      <div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
          {t('hltv.progress')}
        </div>
        <ProgressBar pct={jobProgress(job)} />
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          columnGap: 16,
          rowGap: 4,
          fontSize: 13,
        }}
      >
        {rows.map(([label, value]) => (
          <Fragment key={label}>
            <span className="muted">{label}</span>
            <span>{value}</span>
          </Fragment>
        ))}
      </div>
      {job.error && <p className="error" style={{ margin: 0 }}>{job.error}</p>}
    </div>
  )
}

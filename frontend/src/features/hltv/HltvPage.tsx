import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from '@/features/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/format'
import type { DateRange, TeamHit, Visibility } from '@/types/api'
import { TeamSearch } from './TeamSearch'
import { useDownloadJobs, useStartDownload } from './hooks'

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
  const [error, setError] = useState<string | null>(null)

  const start = useStartDownload()
  const { data: jobs } = useDownloadJobs()

  async function onStart() {
    if (!team) return
    setError(null)
    try {
      await start.mutateAsync({
        team_id: team.id,
        team_name: team.name,
        date_range: dateRange,
        visibility,
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
            </div>
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
                <th>{t('demos.team')}</th>
                <th>{t('demos.status')}</th>
                <th>{t('hltv.matches')}</th>
                <th>{t('hltv.ingested')}</th>
                <th>{t('demos.created')}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.team_name ?? job.team_id}</td>
                  <td>
                    <StatusBadge status={job.status} />
                    {job.error && <div className="error">{job.error}</div>}
                  </td>
                  <td>{job.matches}</td>
                  <td>{job.demos_ingested}</td>
                  <td className="muted">{formatDate(job.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from '@/features/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/format'
import type { DateRange, DownloadJobOut, TeamHit } from '@/types/api'
import { TeamSearch } from './TeamSearch'
import { useDownloadJobs, useJobAction, useStartDownload } from './hooks'

// Overall progress: matches are the stable unit (the demo total only grows as each archive is downloaded)
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

const MAPS = [
  'de_ancient',
  'de_anubis',
  'de_cache',
  'de_dust2',
  'de_inferno',
  'de_mirage',
  'de_nuke',
  'de_overpass',
  'de_train',
  'de_vertigo',
]
const mapLabel = (id: string) => {
  const bare = id.replace(/^de_/, '')
  return bare.charAt(0).toUpperCase() + bare.slice(1)
}

export function HltvPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [team, setTeam] = useState<TeamHit | null>(null)
  const [mapId, setMapId] = useState<string>('')
  const [dateRange, setDateRange] = useState<DateRange>('last_3_months')
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
        map_id: mapId || undefined,
        date_range: dateRange,
        max_matches: maxMatches,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-[1.4rem]">{t('hltv.title')}</h1>

      {!isAdmin && <p className="my-2 text-[0.9rem] text-danger">{t('hltv.adminOnly')}</p>}

      <div
        className={`mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid ${
          isAdmin ? '' : 'opacity-50'
        }`}
      >
        <TeamSearch onSelect={setTeam} />

        {team && (
          <>
            <p className="my-4">
              {t('hltv.selectTeam')}: <strong>{team.name}</strong> (#{team.id})
            </p>
            <div className="flex max-w-[520px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
              <div>
                <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="map">{t('hltv.map')}</label>
                <select id="map" className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text" value={mapId} onChange={(e) => setMapId(e.target.value)}>
                  <option value="">{t('hltv.allMaps')}</option>
                  {MAPS.map((m) => (
                    <option key={m} value={m}>
                      {mapLabel(m)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="range">{t('hltv.dateRange')}</label>
                <select
                  id="range"
                  className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
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
                <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="maxm">{t('hltv.maxMatches')}</label>
                <input
                  id="maxm"
                  className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
                  type="number"
                  min={1}
                  max={200}
                  value={maxMatches}
                  onChange={(e) => setMaxMatches(Math.max(1, Math.min(200, +e.target.value || 1)))}
                />
              </div>
            </div>
            <p className="mt-1 mb-4 text-[13px] text-muted">{t('hltv.maxMatchesHint')}</p>
            {error && <p className="my-2 text-[0.9rem] text-danger">{error}</p>}
            <button className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" onClick={onStart} disabled={!isAdmin || start.isPending}>
              {t('hltv.startDownload')}
            </button>
          </>
        )}
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('hltv.jobs')}</h2>
        {!jobs || jobs.length === 0 ? (
          <p className="my-4 text-muted">{t('hltv.noJobs')}</p>
        ) : (
          <table className="w-full border-collapse text-[0.9rem]">
            <thead>
              <tr>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted w-6"></th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.team')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.status')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('hltv.matches')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('hltv.ingested')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.created')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const open = !!openJobs[job.id]
                return (
                  <Fragment key={job.id}>
                    <tr
                      onClick={() => toggleJob(job.id)}
                      className="cursor-pointer"
                    >
                      <td className="border-b border-border px-2.5 py-2 text-center text-muted">
                        {open ? '▾' : '▸'}
                      </td>
                      <td className="border-b border-border px-2.5 py-2 text-left">{job.team_name ?? job.team_id}</td>
                      <td className="border-b border-border px-2.5 py-2 text-left">
                        <StatusBadge status={job.status} />
                        {job.error && <div className="my-2 text-[0.9rem] text-danger">{job.error}</div>}
                        {job.status === 'completed' &&
                          job.matches_total === 0 &&
                          job.demos_ingested === 0 && (
                            <div className="mt-1 text-xs text-muted">
                              {job.matches_found > 0 && job.map_id
                                ? t('hltv.noMapMatches', {
                                    n: job.matches_found,
                                    map: mapLabel(job.map_id),
                                  })
                                : t('hltv.noMatches')}
                            </div>
                          )}
                      </td>
                      <td className="border-b border-border px-2.5 py-2 text-left">
                        {job.matches_total ? `${job.matches}/${job.matches_total}` : job.matches}
                      </td>
                      <td className="border-b border-border px-2.5 py-2 text-left">
                        {job.demos_total
                          ? `${job.demos_ingested}/${job.demos_total}`
                          : job.demos_ingested}
                      </td>
                      <td className="border-b border-border px-2.5 py-2 text-left text-muted">{formatDate(job.created_at)}</td>
                      <td className="border-b border-border px-2.5 py-2 text-left" onClick={(e) => e.stopPropagation()}>
                        <JobActions job={job} disabled={!isAdmin} />
                      </td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={7} className="border-b border-border px-2.5 py-2 text-left bg-white/2">
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

function JobActions({ job, disabled }: { job: DownloadJobOut; disabled: boolean }) {
  const { t } = useTranslation()
  const action = useJobAction()
  const run = (a: 'pause' | 'resume' | 'cancel' | 'retry') =>
    action.mutate({ id: job.id, action: a })
  const busy = disabled || action.isPending

  const buttons: { label: string; a: 'pause' | 'resume' | 'cancel' | 'retry' }[] = []
  if (job.status === 'running') buttons.push({ label: t('hltv.pause'), a: 'pause' })
  if (job.status === 'paused') buttons.push({ label: t('hltv.resume'), a: 'resume' })
  if (job.status === 'running' || job.status === 'paused' || job.status === 'pending')
    buttons.push({ label: t('common.cancel'), a: 'cancel' })
  if (job.status === 'failed' || job.status === 'cancelled')
    buttons.push({ label: t('hltv.retry'), a: 'retry' })

  if (buttons.length === 0) return null
  return (
    <div className="flex gap-1.5">
      {buttons.map(({ label, a }) => (
        <button
          key={a}
          className="cursor-pointer rounded-md border-none bg-accent px-2 py-0.5 font-[inherit] text-xs text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={() => run(a)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="relative h-[18px] overflow-hidden rounded-[9px] bg-white/8">
      <div
        className="h-full bg-accent transition-[width] duration-300 ease-[ease]"
        style={{ width: `${pct}%` }}
      />
      <span
        className="absolute inset-0 flex items-center justify-center text-xs font-semibold"
      >
        {pct}%
      </span>
    </div>
  )
}

function JobDetails({ job }: { job: DownloadJobOut }) {
  const { t } = useTranslation()
  const narrowed = job.matches_found > job.matches_total
  const rows: [string, string][] = [
    [t('hltv.matches'), job.matches_total ? `${job.matches} / ${job.matches_total}` : `${job.matches}`],
    ...(narrowed
      ? ([[t('hltv.matchesFound'), `${job.matches_found}`]] as [string, string][])
      : []),
    [t('hltv.demos'), job.demos_total ? `${job.demos_ingested} / ${job.demos_total}` : `${job.demos_ingested}`],
    [t('hltv.map'), job.map_id ? mapLabel(job.map_id) : t('hltv.allMaps')],
    [t('hltv.dateRange'), t(`hltv.range.${job.date_range}`, job.date_range)],
    [t('demos.visibility'), job.visibility],
    [t('demos.created'), formatDate(job.created_at)],
    [t('hltv.updated'), formatDate(job.updated_at)],
  ]
  return (
    <div className="flex flex-col gap-2.5 px-1 py-2">
      <div>
        <div className="text-muted mb-1 text-xs">
          {t('hltv.progress')}
        </div>
        <ProgressBar pct={jobProgress(job)} />
      </div>
      <div
        className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]"
      >
        {rows.map(([label, value]) => (
          <Fragment key={label}>
            <span className="text-muted">{label}</span>
            <span>{value}</span>
          </Fragment>
        ))}
      </div>
      {narrowed && job.map_id && (
        <p className="text-muted m-0 text-xs">{t('hltv.matchesHint')}</p>
      )}
      {job.error && <p className="m-0 text-[0.9rem] text-danger">{job.error}</p>}
    </div>
  )
}

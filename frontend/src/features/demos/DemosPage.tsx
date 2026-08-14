import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { formatBytes, formatDate, formatDay } from '@/lib/format'
import { useAuth } from '@/features/auth/AuthContext'
import { useMaps } from '@/features/maps/hooks'
import { UploadDemoForm } from './UploadDemoForm'
import { useDemos, useReparseAll, useReparseStatus } from './hooks'

const PAGE_SIZE = 25

export function DemosPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { data: maps } = useMaps()
  const [mapId, setMapId] = useState('')
  const [team, setTeam] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)

  const reset = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v)
    setPage(0)
  }

  const { data, isLoading, isError } = useDemos({
    map_id: mapId || undefined,
    team: team || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const noDemosAtAll = total === 0 && !(mapId || team || dateFrom || dateTo)

  const reparseAll = useReparseAll()
  const reparseStatus = useReparseStatus(isAdmin)
  const job = reparseStatus.data
  const selectedMapName = maps?.find((m) => m.id === mapId)?.name

  return (
    <div>
      <h1 className="mb-4 text-[1.4rem]">{t('demos.title')}</h1>
      <UploadDemoForm />

      {isAdmin && (
        <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
          <div className="flex flex-wrap items-center gap-3">
            <button
              className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => reparseAll.mutate(mapId || undefined)}
              disabled={reparseAll.isPending || !!job?.running}
            >
              {job?.running
                ? t('demos.reparsing')
                : mapId
                  ? t('demos.reparseMap', { map: selectedMapName ?? mapId })
                  : t('demos.reparseAll')}
            </button>
            {job && (job.running || job.total > 0) && (
              <span className="text-muted text-[13px]">
                {job.done}/{job.total}
                {job.failed > 0 ? ` · ${t('demos.reparseFailed', { n: job.failed })}` : ''}
                {!job.running && job.total > 0 ? ` · ${t('demos.reparseDone')}` : ''}
              </span>
            )}
          </div>
          {job && job.total > 0 && (
            <div className="mt-2 h-2 rounded bg-[#1f2937]">
              <div
                className={`h-full rounded transition-[width] duration-300 ease-[ease] ${
                  job.running ? 'bg-accent' : 'bg-[#10b981]'
                }`}
                style={{ width: `${(job.done / job.total) * 100}%` }}
              />
            </div>
          )}
          <p className="mt-2 mb-0 text-xs text-muted">{t('demos.reparseHint')}</p>
        </div>
      )}

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <select className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text" value={mapId} onChange={(e) => reset(setMapId)(e.target.value)}>
            <option value="">{t('demos.allMaps', 'Todos los mapas')}</option>
            {maps?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <input
            type="search"
            value={team}
            onChange={(e) => reset(setTeam)(e.target.value)}
            placeholder={t('demos.search')}
            className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text max-w-[220px]"
          />
          <label className="mb-1 block text-xs text-muted">
            {t('demos.from', 'Desde')}
            <input className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text" type="date" value={dateFrom} onChange={(e) => reset(setDateFrom)(e.target.value)} />
          </label>
          <label className="mb-1 block text-xs text-muted">
            {t('demos.to', 'Hasta')}
            <input className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text" type="date" value={dateTo} onChange={(e) => reset(setDateTo)(e.target.value)} />
          </label>
        </div>

        {isLoading && <p className="my-4 text-muted">{t('common.loading')}</p>}
        {isError && <p className="my-2 text-[0.9rem] text-danger">{t('common.error')}</p>}
        {!isLoading && !isError && items.length === 0 && (
          <p className="my-4 text-muted">{noDemosAtAll ? t('demos.empty') : t('demos.noMatches')}</p>
        )}
        {items.length > 0 && (
          <>
            <table className="w-full border-collapse text-[0.9rem]">
              <thead>
                <tr>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.map')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.team')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.opponent')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.event')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.matchDate')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.source')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.status')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.size')}</th>
                  <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.created')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((d) => (
                  <tr key={d.id}>
                    <td className="border-b border-border px-2.5 py-2 text-left">
                      <Link className="no-underline text-accent hover:underline" to={`/demos/${d.id}`}>{d.map_id ?? t('common.none')}</Link>
                    </td>
                    <td className="border-b border-border px-2.5 py-2 text-left">{d.team ?? t('common.none')}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left">{d.opponent ?? t('common.none')}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left">{d.event ?? t('common.none')}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left text-muted">{formatDay(d.match_date)}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left">{d.source}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left">
                      <StatusBadge status={d.status} />
                    </td>
                    <td className="border-b border-border px-2.5 py-2 text-left">{formatBytes(d.size_bytes)}</td>
                    <td className="border-b border-border px-2.5 py-2 text-left text-muted">{formatDate(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="mt-3 flex items-center gap-3">
              <button className="cursor-pointer rounded-md border border-border bg-transparent px-3.5 py-2 font-[inherit] text-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                ← {t('demos.prev', 'Anterior')}
              </button>
              <span className="text-muted">
                {t('demos.page', 'Página')} {page + 1}/{pages} · {total}
              </span>
              <button
                className="cursor-pointer rounded-md border border-border bg-transparent px-3.5 py-2 font-[inherit] text-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={page + 1 >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('demos.next', 'Siguiente')} →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

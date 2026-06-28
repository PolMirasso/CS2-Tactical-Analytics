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

  const reparseAll = useReparseAll()
  const reparseStatus = useReparseStatus(isAdmin)
  const job = reparseStatus.data
  const selectedMapName = maps?.find((m) => m.id === mapId)?.name

  return (
    <div>
      <h1>{t('demos.title')}</h1>
      <UploadDemoForm />

      {isAdmin && (
        <div className="card">
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
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
              <span className="muted" style={{ fontSize: 13 }}>
                {job.done}/{job.total}
                {job.failed > 0 ? ` · ${t('demos.reparseFailed', { n: job.failed })}` : ''}
                {!job.running && job.total > 0 ? ` · ${t('demos.reparseDone')}` : ''}
              </span>
            )}
          </div>
          {job && job.total > 0 && (
            <div style={{ background: '#1f2937', borderRadius: 4, height: 8, marginTop: 8 }}>
              <div
                style={{
                  width: `${(job.done / job.total) * 100}%`,
                  height: '100%',
                  background: job.running ? 'var(--accent, #4f8cff)' : '#10b981',
                  borderRadius: 4,
                  transition: 'width 0.3s',
                }}
              />
            </div>
          )}
          <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>{t('demos.reparseHint')}</p>
        </div>
      )}

      <div className="card">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <select value={mapId} onChange={(e) => reset(setMapId)(e.target.value)}>
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
            style={{ maxWidth: 220 }}
          />
          <label className="muted" style={{ fontSize: 12 }}>
            {t('demos.from', 'Desde')}
            <input type="date" value={dateFrom} onChange={(e) => reset(setDateFrom)(e.target.value)} />
          </label>
          <label className="muted" style={{ fontSize: 12 }}>
            {t('demos.to', 'Hasta')}
            <input type="date" value={dateTo} onChange={(e) => reset(setDateTo)(e.target.value)} />
          </label>
        </div>

        {isLoading && <p className="muted">{t('common.loading')}</p>}
        {isError && <p className="error">{t('common.error')}</p>}
        {!isLoading && items.length === 0 && <p className="muted">{t('demos.noMatches')}</p>}
        {items.length > 0 && (
          <>
            <table>
              <thead>
                <tr>
                  <th>{t('demos.map')}</th>
                  <th>{t('demos.team')}</th>
                  <th>{t('demos.opponent')}</th>
                  <th>{t('demos.event')}</th>
                  <th>{t('demos.matchDate')}</th>
                  <th>{t('demos.source')}</th>
                  <th>{t('demos.status')}</th>
                  <th>{t('demos.size')}</th>
                  <th>{t('demos.created')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/demos/${d.id}`}>{d.map_id ?? t('common.none')}</Link>
                    </td>
                    <td>{d.team ?? t('common.none')}</td>
                    <td>{d.opponent ?? t('common.none')}</td>
                    <td>{d.event ?? t('common.none')}</td>
                    <td className="muted">{formatDay(d.match_date)}</td>
                    <td>{d.source}</td>
                    <td>
                      <StatusBadge status={d.status} />
                    </td>
                    <td>{formatBytes(d.size_bytes)}</td>
                    <td className="muted">{formatDate(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
              <button className="ghost" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                ← {t('demos.prev', 'Anterior')}
              </button>
              <span className="muted">
                {t('demos.page', 'Página')} {page + 1}/{pages} · {total}
              </span>
              <button
                className="ghost"
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

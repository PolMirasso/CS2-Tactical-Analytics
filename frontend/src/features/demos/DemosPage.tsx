import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { formatBytes, formatDate, formatDay } from '@/lib/format'
import { UploadDemoForm } from './UploadDemoForm'
import { useDemos } from './hooks'

export function DemosPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useDemos()
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    if (!data) return data
    const q = query.trim().toLowerCase()
    if (!q) return data
    return data.filter((d) =>
      [d.team, d.opponent, d.map_id, d.event].some((field) =>
        field?.toLowerCase().includes(q),
      ),
    )
  }, [data, query])

  return (
    <div>
      <h1>{t('demos.title')}</h1>
      <UploadDemoForm />

      <div className="card">
        {isLoading && <p className="muted">{t('common.loading')}</p>}
        {isError && <p className="error">{t('common.error')}</p>}
        {data && data.length === 0 && <p className="muted">{t('demos.empty')}</p>}
        {data && data.length > 0 && (
          <>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('demos.search')}
              style={{ marginBottom: 12, maxWidth: 320 }}
            />
            {filtered && filtered.length === 0 ? (
              <p className="muted">{t('demos.noMatches')}</p>
            ) : (
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
                  {filtered?.map((d) => (
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
            )}
          </>
        )}
      </div>
    </div>
  )
}

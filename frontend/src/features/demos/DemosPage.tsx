import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { formatBytes, formatDate } from '@/lib/format'
import { UploadDemoForm } from './UploadDemoForm'
import { useDemos } from './hooks'

export function DemosPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useDemos()

  return (
    <div>
      <h1>{t('demos.title')}</h1>
      <UploadDemoForm />

      <div className="card">
        {isLoading && <p className="muted">{t('common.loading')}</p>}
        {isError && <p className="error">{t('common.error')}</p>}
        {data && data.length === 0 && <p className="muted">{t('demos.empty')}</p>}
        {data && data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>{t('demos.map')}</th>
                <th>{t('demos.team')}</th>
                <th>{t('demos.opponent')}</th>
                <th>{t('demos.source')}</th>
                <th>{t('demos.status')}</th>
                <th>{t('demos.size')}</th>
                <th>{t('demos.created')}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link to={`/demos/${d.id}`}>{d.map_id ?? t('common.none')}</Link>
                  </td>
                  <td>{d.team ?? t('common.none')}</td>
                  <td>{d.opponent ?? t('common.none')}</td>
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
      </div>
    </div>
  )
}

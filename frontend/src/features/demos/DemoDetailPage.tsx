import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { formatBytes, formatDate } from '@/lib/format'
import { useDemo, useDeleteDemo, useReparseDemo } from './hooks'

export function DemoDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams()
  const demoId = Number(id)
  const navigate = useNavigate()
  const { data: demo, isLoading, isError } = useDemo(demoId)
  const reparse = useReparseDemo()
  const remove = useDeleteDemo()

  if (isLoading) return <p className="muted">{t('common.loading')}</p>
  if (isError || !demo) return <p className="error">{t('common.error')}</p>

  async function onDelete() {
    if (!confirm(t('demos.deleteConfirm'))) return
    await remove.mutateAsync(demoId)
    navigate('/')
  }

  const rows: [string, string][] = [
    [t('demos.map'), demo.map_id ?? t('common.none')],
    [t('demos.team'), demo.team ?? t('common.none')],
    [t('demos.opponent'), demo.opponent ?? t('common.none')],
    [t('demos.event'), demo.event ?? t('common.none')],
    [t('demos.source'), demo.source],
    [t('demos.visibility'), demo.visibility],
    [t('demos.size'), formatBytes(demo.size_bytes)],
    [t('demos.created'), formatDate(demo.created_at)],
  ]

  return (
    <div>
      <h1>
        {demo.team ?? t('common.none')} {demo.opponent ? `vs ${demo.opponent}` : ''}{' '}
        <StatusBadge status={demo.status} />
      </h1>

      <div className="card">
        <table>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th style={{ width: 160 }}>{k}</th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {demo.error && <p className="error">{demo.error}</p>}
      </div>

      <div className="card">
        <div className="row" style={{ maxWidth: 360 }}>
          <button
            className="ghost"
            onClick={() => reparse.mutate(demoId)}
            disabled={reparse.isPending}
          >
            {t('demos.reparse')}
          </button>
          <button className="danger" onClick={onDelete} disabled={remove.isPending}>
            {t('common.delete')}
          </button>
        </div>
        {reparse.data && (
          <p className="muted" style={{ marginTop: 12 }}>
            {t('demos.uploaded', {
              rounds: reparse.data.rounds,
              utility: reparse.data.utility_events,
            })}
          </p>
        )}
      </div>
    </div>
  )
}

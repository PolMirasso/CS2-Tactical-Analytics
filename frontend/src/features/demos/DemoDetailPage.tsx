import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { formatBytes, formatDate } from '@/lib/format'
import { RoundsTable } from './RoundsTable'
import { PlayerScoreboard, WinRateSummary } from './MatchStats'
import { useDemo, useDemoAnalysis, useDeleteDemo, useReparseDemo } from './hooks'

export function DemoDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams()
  const demoId = Number(id)
  const navigate = useNavigate()
  const { data: demo, isLoading, isError } = useDemo(demoId)
  const analysis = useDemoAnalysis(demoId)
  const reparse = useReparseDemo()
  const remove = useDeleteDemo()

  if (isLoading) return <p className="text-muted">{t('common.loading')}</p>
  if (isError || !demo) return <p className="my-2 text-[0.9rem] text-danger">{t('common.error')}</p>

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
        <StatusBadge status={reparse.isPending ? 'reparsing' : demo.status} />
      </h1>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <table>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th className="w-40">{k}</th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {demo.error && <p className="my-2 text-[0.9rem] text-danger">{demo.error}</p>}
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <div className="flex max-w-[360px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
          <button
            className="border border-border bg-transparent text-text"
            onClick={() => reparse.mutate(demoId)}
            disabled={reparse.isPending}
          >
            {t('demos.reparse')}
          </button>
          <button className="bg-danger" onClick={onDelete} disabled={remove.isPending}>
            {t('common.delete')}
          </button>
        </div>
        {reparse.data && (
          <p className="text-muted mt-3">
            {t('demos.uploaded', {
              rounds: reparse.data.rounds,
              utility: reparse.data.utility_events,
            })}
          </p>
        )}
      </div>

      {demo.status === 'parsed' && (
        <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
          <Link to={`/demos/${demoId}/replay`} className="inline-block cursor-pointer rounded-md bg-accent px-3.5 py-2 text-accent-text hover:brightness-[1.08]">
            {t('replay.open')}
          </Link>
        </div>
      )}

      {analysis.isLoading && <p className="text-muted">{t('common.loading')}</p>}
      {analysis.data && (
        <>
          <PlayerScoreboard players={analysis.data.players} />
          <WinRateSummary rounds={analysis.data.rounds} />
          <RoundsTable rounds={analysis.data.rounds} />
        </>
      )}
    </div>
  )
}

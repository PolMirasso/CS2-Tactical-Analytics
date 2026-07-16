import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Replay2D } from './Replay2D'
import { useDemo } from './hooks'

export function ReplayPage() {
  const { t } = useTranslation()
  const { id } = useParams()
  const demoId = Number(id)
  const { data: demo } = useDemo(demoId)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3.5">
        <Link to={`/demos/${demoId}`} className="inline-block rounded-md border border-border px-3 py-1.5 text-text hover:bg-surface-2">
          ← {t('replay.back')}
        </Link>
        {demo && (
          <span className="text-muted">
            {demo.team ?? ''} {demo.opponent ? `vs ${demo.opponent}` : ''} · {demo.map_id ?? ''}
          </span>
        )}
      </div>
      <Replay2D demoId={demoId} fullscreen />
    </div>
  )
}

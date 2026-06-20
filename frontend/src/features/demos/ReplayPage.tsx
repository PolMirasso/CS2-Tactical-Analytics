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
    <div className="replay-page">
      <div className="replay-page-head">
        <Link to={`/demos/${demoId}`} className="ghost back-link">
          ← {t('replay.back')}
        </Link>
        {demo && (
          <span className="muted">
            {demo.team ?? ''} {demo.opponent ? `vs ${demo.opponent}` : ''} · {demo.map_id ?? ''}
          </span>
        )}
      </div>
      <Replay2D demoId={demoId} fullscreen />
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from '@/features/auth/AuthContext'
import type { Visibility } from '@/types/api'
import { useUploadDemo } from './hooks'

export function UploadDemoForm() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const upload = useUploadDemo()
  const [file, setFile] = useState<File | null>(null)
  const [map, setMap] = useState('')
  const [team, setTeam] = useState('')
  const [opponent, setOpponent] = useState('')
  const [event, setEvent] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('private')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    form.append('visibility', visibility)
    if (map) form.append('map_id', map)
    if (team) form.append('team', team)
    if (opponent) form.append('opponent', opponent)
    if (event) form.append('event', event)
    try {
      const res = await upload.mutateAsync(form)
      setNote(
        t('demos.uploaded', { rounds: res.rounds, utility: res.utility_events }),
      )
      setFile(null)
      ;(e.target as HTMLFormElement).reset()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    }
  }

  return (
    <div className="card">
      <h2>{t('demos.uploadTitle')}</h2>
      <form onSubmit={onSubmit}>
        <label htmlFor="file">{t('demos.file')}</label>
        <input
          id="file"
          type="file"
          accept=".dem"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        <div className="row">
          <div>
            <label htmlFor="map">{t('demos.map')}</label>
            <input
              id="map"
              placeholder="de_mirage"
              value={map}
              onChange={(e) => setMap(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="team">{t('demos.team')}</label>
            <input id="team" value={team} onChange={(e) => setTeam(e.target.value)} />
          </div>
          <div>
            <label htmlFor="opponent">{t('demos.opponent')}</label>
            <input
              id="opponent"
              value={opponent}
              onChange={(e) => setOpponent(e.target.value)}
            />
          </div>
        </div>
        <div className="row">
          <div>
            <label htmlFor="event">{t('demos.event')}</label>
            <input id="event" value={event} onChange={(e) => setEvent(e.target.value)} />
          </div>
          <div>
            <label htmlFor="visibility">{t('demos.visibility')}</label>
            <select
              id="visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
            >
              <option value="private">private</option>
              <option value="public" disabled={user?.role !== 'admin'}>
                public {user?.role !== 'admin' ? '(admin)' : ''}
              </option>
            </select>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {note && <p className="muted">{note}</p>}
        <button type="submit" disabled={upload.isPending || !file}>
          {t('common.submit')}
        </button>
      </form>
    </div>
  )
}

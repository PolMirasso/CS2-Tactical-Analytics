import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from '@/features/auth/AuthContext'
import type { Visibility } from '@/types/api'
import { useDemoEvents, useUploadDemo } from './hooks'

export function UploadDemoForm() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const upload = useUploadDemo()
  const events = useDemoEvents()
  const [file, setFile] = useState<File | null>(null)
  const [event, setEvent] = useState('')
  const [matchDate, setMatchDate] = useState('')
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
    form.append('visibility', isAdmin ? visibility : 'private')
    if (event) form.append('event', event)
    if (matchDate) form.append('match_date', matchDate)
    try {
      const res = await upload.mutateAsync(form)
      setNote(
        t(res.duplicate ? 'demos.duplicateNote' : 'demos.uploaded', {
          rounds: res.rounds,
          utility: res.utility_events,
        }),
      )
      setFile(null)
      ;(e.target as HTMLFormElement).reset()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    }
  }

  return (
    <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
      <h2 className="mb-3 text-[1.1rem]">{t('demos.uploadTitle')}</h2>
      <form onSubmit={onSubmit}>
        <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="file">{t('demos.file')}</label>
        <input
          id="file"
          className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
          type="file"
          accept=".dem"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        <p className="my-4 text-muted">{t('demos.mapAutoDetected')}</p>
        <div className="flex flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
          <div>
            <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="matchDate">{t('demos.matchDate')}</label>
            <input
              id="matchDate"
              className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
              type="date"
              value={matchDate}
              onChange={(e) => setMatchDate(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="event">{t('demos.event')}</label>
            <input
              id="event"
              className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
              list="event-options"
              autoComplete="off"
              value={event}
              onChange={(e) => setEvent(e.target.value)}
            />
            <datalist id="event-options">
              {(events.data ?? []).map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>
          {isAdmin && (
            <div>
              <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="visibility">{t('demos.visibility')}</label>
              <select
                id="visibility"
                className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
                value={visibility}
                onChange={(e) => setVisibility(e.target.value as Visibility)}
              >
                <option value="private">private</option>
                <option value="public">public</option>
              </select>
            </div>
          )}
        </div>
        {error && <p className="my-2 text-[0.9rem] text-danger">{error}</p>}
        {note && <p className="my-4 text-muted">{note}</p>}
        <button className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" type="submit" disabled={upload.isPending || !file}>
          {t('common.submit')}
        </button>
      </form>
    </div>
  )
}

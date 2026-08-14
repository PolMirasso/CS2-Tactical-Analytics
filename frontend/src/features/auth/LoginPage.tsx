import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/apiClient'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto mt-[12vh] max-w-[360px]">
      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h1 className="mb-4 text-[1.4rem]">{t('auth.loginTitle')}</h1>
        <form onSubmit={onSubmit}>
          <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="email">{t('auth.email')}</label>
          <input
            id="email"
            className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="password">{t('auth.password')}</label>
          <input
            id="password"
            className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="my-2 text-[0.9rem] text-danger">{error}</p>}
          <button className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" type="submit" disabled={busy}>
            {t('auth.login')}
          </button>
        </form>
        <p className="mt-3 mb-4 text-muted">
          <Link className="no-underline text-accent hover:underline" to="/register">{t('auth.needAccount')}</Link>
        </p>
      </div>
    </div>
  )
}

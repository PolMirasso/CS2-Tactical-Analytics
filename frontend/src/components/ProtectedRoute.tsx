import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const { t } = useTranslation()

  if (loading) return <div className="grid min-h-[60vh] place-items-center text-muted">{t('common.loading')}</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

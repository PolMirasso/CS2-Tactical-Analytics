import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/AuthContext'
import { LanguageSwitcher } from './LanguageSwitcher'

export function NavBar() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()

  return (
    <header className="navbar">
      <span className="brand">{t('app.title')}</span>
      <nav>
        <NavLink to="/" end>
          {t('nav.demos')}
        </NavLink>
        <NavLink to="/hltv">{t('nav.hltv')}</NavLink>
        <NavLink to="/groups">{t('nav.groups')}</NavLink>
        <NavLink to="/maps">{t('nav.maps')}</NavLink>
      </nav>
      <span className="spacer" />
      <LanguageSwitcher />
      {user && <span className="muted">{user.email}</span>}
      <button className="ghost" onClick={logout}>
        {t('nav.logout')}
      </button>
    </header>
  )
}

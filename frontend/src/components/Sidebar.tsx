import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/AuthContext'
import { LanguageSwitcher } from './LanguageSwitcher'

const icon = (path: string): ReactNode => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={path} />
  </svg>
)

const NAV: { to: string; end?: boolean; key: string; icon: ReactNode }[] = [
  { to: '/', end: true, key: 'nav.demos', icon: icon('M10 8l6 4-6 4V8zM4 4h16v16H4z') },
  { to: '/analytics', key: 'nav.analytics', icon: icon('M3 3v18h18M7 14l4-4 3 3 5-6') },
  { to: '/scouting', key: 'nav.scouting', icon: icon('M12 2v3m0 14v3M2 12h3m14 0h3M12 7a5 5 0 100 10 5 5 0 000-10z') },
  { to: '/hltv', key: 'nav.hltv', icon: icon('M12 3v12m0 0l-4-4m4 4l4-4M5 21h14') },
  { to: '/groups', key: 'nav.groups', icon: icon('M17 21v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zm12 10v-2a4 4 0 00-3-3.87M16 3.13A4 4 0 0118 11') },
  { to: '/maps', key: 'nav.maps', icon: icon('M9 4L3 7v13l6-3 6 3 6-3V4l-6 3-6-3zm0 0v13m6-10v13') },
  { to: '/maps/edit', key: 'nav.mapEditor', icon: icon('M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4 12.5-12.5z') },
]

const STORAGE_KEY = 'cs2.sidebar.collapsed'

export function Sidebar() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(STORAGE_KEY) === '1')

  const toggle = () => {
    setCollapsed((c) => {
      localStorage.setItem(STORAGE_KEY, c ? '0' : '1')
      return !c
    })
  }

  return (
    <aside
      className={`sticky top-0 flex h-screen shrink-0 flex-col gap-1.5 self-start overflow-y-auto border-r border-border bg-surface px-2.5 py-3 transition-[width] duration-150 ease-[ease] print:hidden ${
        collapsed ? 'w-[60px]' : 'w-[220px]'
      }`}
    >
      <div
        className={`mb-2 flex min-h-[34px] items-center gap-2 ${
          collapsed ? 'justify-center' : 'justify-between'
        }`}
      >
        {!collapsed && <span className="overflow-hidden font-bold whitespace-nowrap">{t('app.title')}</span>}
        <button
          className="border border-border bg-transparent px-[9px] py-0.5 text-[18px] leading-none text-text"
          onClick={toggle}
          aria-label="Toggle menu"
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            title={t(item.key)}
            className={({ isActive }) =>
              `flex items-center gap-[11px] rounded-lg whitespace-nowrap ${
                collapsed ? 'justify-center p-[9px]' : 'px-[11px] py-[9px]'
              } ${isActive ? 'bg-accent text-accent-text' : 'text-text hover:bg-surface-2'}`
            }
          >
            <span className="inline-flex shrink-0">{item.icon}</span>
            {!collapsed && <span>{t(item.key)}</span>}
          </NavLink>
        ))}
      </nav>

      <div className={`mt-auto flex flex-col gap-2 ${collapsed ? 'items-center' : ''}`}>
        {!collapsed && <LanguageSwitcher />}
        {user && !collapsed && (
          <span className="overflow-hidden text-xs text-ellipsis whitespace-nowrap text-muted">{user.email}</span>
        )}
        <button
          className="border border-border bg-transparent text-text"
          onClick={logout}
          title={t('nav.logout')}
        >
          {collapsed ? '⎋' : t('nav.logout')}
        </button>
      </div>
    </aside>
  )
}

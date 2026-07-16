import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="flex min-h-screen print:block">
      <Sidebar />
      <main className="min-w-0 flex-1 px-6 pt-5 pb-14 print:p-0">
        <Outlet />
      </main>
    </div>
  )
}

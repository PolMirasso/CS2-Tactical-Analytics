import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { DemosPage } from '@/features/demos/DemosPage'
import { DemoDetailPage } from '@/features/demos/DemoDetailPage'
import { ReplayPage } from '@/features/demos/ReplayPage'
import { HltvPage } from '@/features/hltv/HltvPage'
import { GroupsPage } from '@/features/groups/GroupsPage'
import { MapsPage } from '@/features/maps/MapsPage'
import { MapEditorPage } from '@/features/maps/MapEditorPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  {
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <DemosPage /> },
      { path: 'demos/:id', element: <DemoDetailPage /> },
      { path: 'demos/:id/replay', element: <ReplayPage /> },
      { path: 'hltv', element: <HltvPage /> },
      { path: 'groups', element: <GroupsPage /> },
      { path: 'maps', element: <MapsPage /> },
      { path: 'maps/edit', element: <MapEditorPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

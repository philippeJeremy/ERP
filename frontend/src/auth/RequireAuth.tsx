import { Navigate, Outlet, useLocation } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { FullPageSpinner } from '@/components/layout/FullPageSpinner'

/** Protège les routes : sans session, redirection vers /login (en mémorisant la page demandée). */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <FullPageSpinner />
  if (status === 'anonymous') {
    const next = location.pathname + location.search
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }
  return <Outlet />
}

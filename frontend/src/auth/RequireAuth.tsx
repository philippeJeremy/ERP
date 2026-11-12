import { Navigate, Outlet, useLocation } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { FullPageSpinner } from '@/components/layout/FullPageSpinner'

const PASSWORD_CHANGE_PATH = '/changer-mot-de-passe'

/** Protège les routes : sans session, redirection vers /login (en mémorisant la page demandée). */
export function RequireAuth() {
  const { status, me } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <FullPageSpinner />
  if (status === 'anonymous') {
    const next = location.pathname + location.search
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }
  // Mot de passe provisoire : une seule page accessible, celle qui permet de le changer.
  // (L'API applique la même règle : contourner cet écran ne donnerait accès à rien.)
  if (me?.user.must_change_password && location.pathname !== PASSWORD_CHANGE_PATH) {
    return <Navigate to={PASSWORD_CHANGE_PATH} replace />
  }
  return <Outlet />
}

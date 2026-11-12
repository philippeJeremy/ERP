import { useContext } from 'react'

import { AuthContext, type AuthContextValue } from '@/auth/context'

/** Accès à l'état de connexion depuis n'importe quel composant. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé dans <AuthProvider>')
  return ctx
}

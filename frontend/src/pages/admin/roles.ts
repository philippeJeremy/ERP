import { useAuth } from '@/auth/useAuth'
import { can } from '@/lib/permissions'
import type { Role } from '@/lib/types'

/** Vrai si l'utilisateur connecté possède toutes les permissions du rôle (règle de l'API :
 * on ne donne pas, et on ne retire pas, plus de droits qu'on n'en a). */
export function useCanGrant() {
  const { me } = useAuth()
  return (role: Role) => role.permissions.every((p) => can(me?.permissions, p))
}

export function describePermissions(role: Role): string {
  if (role.permissions.includes('*')) return 'Tous les droits dans la société'
  if (role.permissions.length === 0) return 'Aucun droit'
  return role.description || role.permissions.join(', ')
}

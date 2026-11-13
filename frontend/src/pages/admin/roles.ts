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

/** Libellés des modules (préfixe des permissions) pour les écrans de droits. */
export const MODULE_LABELS: Record<string, string> = {
  auth: 'Utilisateurs et rôles',
  org: 'Société',
  partners: 'Tiers',
  catalog: 'Articles',
  sales: 'Ventes',
  purchasing: 'Achats',
  inventory: 'Stock',
  invoicing: 'Facturation',
}
export const moduleLabel = (m: string) => MODULE_LABELS[m] ?? m

/** Le rôle donne-t-il ce droit (exact, « module:* » ou « * ») ? */
export function roleCovers(role: Role, permission: string): boolean {
  const module = permission.split(':', 1)[0]
  return role.permissions.some((p) => p === permission || p === `${module}:*` || p === '*')
}

/** Regroupe des permissions par module, dans l'ordre du catalogue. */
export function groupByModule<T extends { code: string }>(items: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const module = item.code.split(':', 1)[0]
    groups.set(module, [...(groups.get(module) ?? []), item])
  }
  return [...groups.entries()]
}

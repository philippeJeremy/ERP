import { CheckRow } from '@/components/ui/field'
import type { Role } from '@/lib/types'
import { describePermissions, useCanGrant } from '@/pages/admin/roles'

export function RolePicker({
  roles,
  value,
  onChange,
  disabled,
  grantableIds,
}: {
  roles: Role[]
  value: number[]
  onChange: (ids: number[]) => void
  disabled?: boolean
  /** Rôles attribuables, calculés par l'API pour une société donnée. Sans cette
   * liste : règle appliquée avec les droits dans la société courante. */
  grantableIds?: number[]
}) {
  const canGrantHere = useCanGrant()
  const canGrant = (role: Role) => (grantableIds ? grantableIds.includes(role.id) : canGrantHere(role))
  return (
    <div className="grid gap-2">
      {roles.map((role) => {
        const allowed = canGrant(role)
        return (
          <CheckRow
            key={role.id}
            checked={value.includes(role.id)}
            disabled={disabled || !allowed}
            onChange={(on) => onChange(on ? [...value, role.id] : value.filter((id) => id !== role.id))}
            title={role.name}
            description={allowed ? describePermissions(role) : "Ce rôle donne des droits que vous n'avez pas"}
          />
        )
      })}
    </div>
  )
}

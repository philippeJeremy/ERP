import { CheckRow } from '@/components/ui/field'
import type { Role } from '@/lib/types'
import { describePermissions, useCanGrant } from '@/pages/admin/roles'

export function RolePicker({
  roles,
  value,
  onChange,
  disabled,
}: {
  roles: Role[]
  value: number[]
  onChange: (ids: number[]) => void
  disabled?: boolean
}) {
  const canGrant = useCanGrant()
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

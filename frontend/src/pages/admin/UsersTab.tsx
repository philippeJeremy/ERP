import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { formatRelative, initials } from '@/lib/format'
import { can } from '@/lib/permissions'
import type { Role, UserInCompany } from '@/lib/types'
import { CreateUserDialog } from '@/pages/admin/CreateUserDialog'
import { EditUserDialog } from '@/pages/admin/EditUserDialog'

export function UsersTab() {
  const { me, company } = useAuth()
  const canManage = can(me?.permissions, 'auth:manage')
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [opened, setOpened] = useState<UserInCompany | null>(null)

  // La clé contient la société : chaque société a sa propre liste en cache.
  const users = useQuery({
    queryKey: ['users', company?.id],
    queryFn: () => api<UserInCompany[]>('/auth/users'),
  })
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/auth/roles') })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = users.data ?? []
    if (!q) return list
    return list.filter(
      (u) =>
        u.full_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.roles.some((r) => r.name.toLowerCase().includes(q)),
    )
  }, [users.data, search])
  // Données à jour si la personne est dans la liste ; sinon (accès à la société courante
  // retiré depuis sa fiche), on garde la fiche ouverte avec les dernières données connues.
  const editing = opened ? (users.data?.find((u) => u.id === opened.id) ?? opened) : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Rechercher un nom, un e-mail, un rôle"
            aria-label="Rechercher un utilisateur"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {users.data ? `${filtered.length} utilisateur${filtered.length > 1 ? 's' : ''}` : ''}
        </p>
        {canManage && (
          <Button className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> Nouvel utilisateur
          </Button>
        )}
      </div>

      <ErrorAlert error={users.error} />

      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Utilisateur</th>
              <th className="px-4 py-2.5 font-medium">Rôles</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Dernière connexion</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.isPending && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  <LoaderCircle className="mx-auto size-5 animate-spin" />
                </td>
              </tr>
            )}
            {users.data && filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  Aucun utilisateur ne correspond à « {search} ».
                </td>
              </tr>
            )}
            {filtered.map((u) => (
              <tr
                key={u.id}
                onClick={() => setOpened(u)}
                className="cursor-pointer transition-colors hover:bg-secondary/40"
              >
                <td className="px-4 py-3">
                  <button type="button" className="flex items-center gap-3 text-left" aria-label={`Ouvrir ${u.full_name}`}>
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold">
                      {initials(u.full_name)}
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-2 font-medium">
                        {u.full_name}
                        {u.id === me?.user.id && <span className="text-xs font-normal text-muted-foreground">(vous)</span>}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">{u.email}</span>
                    </span>
                  </button>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {u.is_superuser && <Badge variant="accent">Super-admin</Badge>}
                    {u.roles.map((r) => (
                      <Badge key={r.id} variant="secondary">
                        {r.name}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {u.is_active ? <Badge variant="success">Actif</Badge> : <Badge variant="outline">Désactivé</Badge>}
                </td>
                <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                  {u.last_login_at ? formatRelative(u.last_login_at) : 'Jamais'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {creating && <CreateUserDialog roles={roles.data ?? []} onClose={() => setCreating(false)} />}
      {editing && (
        <EditUserDialog
          key={editing.id}
          user={editing}
          roles={roles.data ?? []}
          canManage={canManage}
          onClose={() => setOpened(null)}
        />
      )}
    </div>
  )
}

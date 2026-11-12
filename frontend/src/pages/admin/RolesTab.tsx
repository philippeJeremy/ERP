import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Lock, Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import type { PermissionInfo, Role } from '@/lib/types'

const MODULE_LABELS: Record<string, string> = {
  auth: 'Utilisateurs et rôles',
  org: 'Société',
  partners: 'Tiers',
  catalog: 'Articles',
  sales: 'Ventes',
  purchasing: 'Achats',
  inventory: 'Stock',
  invoicing: 'Facturation',
}
const moduleLabel = (m: string) => MODULE_LABELS[m] ?? m

export function RolesTab() {
  const { me } = useAuth()
  const isSuperuser = !!me?.user.is_superuser
  const [editing, setEditing] = useState<Role | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Role | null>(null)

  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/auth/roles') })
  const permissions = useQuery({
    queryKey: ['permissions'],
    queryFn: () => api<PermissionInfo[]>('/auth/permissions'),
    staleTime: Infinity, // le catalogue ne change qu'avec une nouvelle version de l'ERP
  })
  const labels = useMemo(() => new Map(permissions.data?.map((p) => [p.code, p.label])), [permissions.data])

  const describe = (code: string) => {
    if (code === '*') return 'Tous les droits'
    if (code.endsWith(':*')) return `${moduleLabel(code.slice(0, -2))} : tous les droits`
    return labels.get(code) ?? code
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Un rôle regroupe des droits. Les rôles sont communs à toutes les sociétés du groupe ; on les attribue ensuite
          à chaque utilisateur, société par société.
          {!isSuperuser && ' Seul un super-administrateur peut les modifier.'}
        </p>
        {isSuperuser && (
          <Button onClick={() => setEditing('new')}>
            <Plus /> Nouveau rôle
          </Button>
        )}
      </div>
      <ErrorAlert error={roles.error} />
      {roles.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}

      <div className="grid gap-3 lg:grid-cols-2">
        {roles.data?.map((role) => (
          <article key={role.id} className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs">
            <header className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="flex flex-wrap items-center gap-2 font-medium">
                  {role.name}
                  {role.is_system && (
                    <Badge variant="outline">
                      <Lock /> Système
                    </Badge>
                  )}
                </h3>
                <p className="text-xs text-muted-foreground">
                  <span className="font-mono">{role.code}</span> · {role.user_count} utilisateur
                  {role.user_count > 1 ? 's' : ''}
                </p>
              </div>
              {isSuperuser && !role.is_system && (
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="icon" onClick={() => setEditing(role)} aria-label={`Modifier le rôle ${role.name}`} title="Modifier">
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" onClick={() => setDeleting(role)} aria-label={`Supprimer le rôle ${role.name}`} title="Supprimer">
                    <Trash2 />
                  </Button>
                </div>
              )}
            </header>
            {role.description && <p className="text-sm text-muted-foreground">{role.description}</p>}
            <ul className="flex flex-wrap gap-1.5">
              {role.permissions.length === 0 && <li className="text-sm text-muted-foreground">Aucun droit</li>}
              {role.permissions.map((p) => (
                <li key={p}>
                  <Badge variant={p === '*' ? 'accent' : 'secondary'} title={p}>
                    {describe(p)}
                  </Badge>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>

      {editing && (
        <RoleDialog
          role={editing === 'new' ? null : editing}
          permissions={permissions.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && <DeleteRoleDialog role={deleting} onClose={() => setDeleting(null)} />}
    </div>
  )
}

/** « Chef des ventes » → « chef_des_ventes » (code technique proposé à partir du nom). */
function slugify(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 50)
}

function RoleDialog({ role, permissions, onClose }: { role: Role | null; permissions: PermissionInfo[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [selected, setSelected] = useState<Set<string>>(new Set(role?.permissions ?? []))

  // Permissions regroupées par module (préfixe avant « : »).
  const modules = useMemo(() => {
    const groups = new Map<string, PermissionInfo[]>()
    for (const p of permissions) {
      const module = p.code.split(':', 1)[0]
      groups.set(module, [...(groups.get(module) ?? []), p])
    }
    return [...groups.entries()]
  }, [permissions])

  const toggle = (code: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (on) next.add(code)
      else next.delete(code)
      return next
    })

  const save = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), description: description.trim() || null, permissions: [...selected] }
      return role
        ? api<Role>(`/auth/roles/${role.id}`, { method: 'PATCH', body })
        : api<Role>('/auth/roles', { method: 'POST', body: { ...body, code: slugify(name) } })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      // Les droits des utilisateurs connectés peuvent avoir changé.
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })
  const valid = name.trim().length > 0 && (role !== null || slugify(name).length > 0)

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{role ? `Modifier « ${role.name} »` : 'Nouveau rôle'}</DialogTitle>
          <DialogDescription>
            {role && role.user_count > 0
              ? `Les changements s'appliquent tout de suite aux ${role.user_count} utilisateur(s) qui ont ce rôle, dans toutes les sociétés.`
              : 'Choisissez les droits que ce rôle donnera.'}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) save.mutate()
          }}
        >
          <Field id="role_name" label="Nom" hint={role ? undefined : name.trim() ? `Code technique : ${slugify(name)}` : 'Par exemple : Commercial, Comptable, Magasinier.'}>
            <Input id="role_name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field id="role_description" label="Description (facultative)">
            <Input id="role_description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>

          <fieldset className="space-y-4">
            <legend className="mb-2 text-sm font-medium">Droits</legend>
            {modules.map(([module, perms]) => {
              const all = selected.has(`${module}:*`)
              return (
                <div key={module} className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <h4 className="text-xs font-medium tracking-wider text-muted-foreground uppercase">{moduleLabel(module)}</h4>
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                      <input type="checkbox" className="size-3.5 accent-[var(--primary)]" checked={all} onChange={(e) => toggle(`${module}:*`, e.target.checked)} />
                      Tout le module (droits futurs compris)
                    </label>
                  </div>
                  <div className="grid gap-2">
                    {perms.map((p) => (
                      <CheckRow
                        key={p.code}
                        checked={all || selected.has(p.code)}
                        disabled={all}
                        onChange={(on) => toggle(p.code, on)}
                        title={p.label}
                        description={<span className="font-mono">{p.code}</span>}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </fieldset>

          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={!valid || save.isPending}>
              {save.isPending && <LoaderCircle className="animate-spin" />}
              {role ? 'Enregistrer' : 'Créer le rôle'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteRoleDialog({ role, onClose }: { role: Role; onClose: () => void }) {
  const queryClient = useQueryClient()
  const remove = useMutation({
    mutationFn: () => api<void>(`/auth/roles/${role.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Supprimer « {role.name} » ?</DialogTitle>
          <DialogDescription>
            {role.user_count > 0
              ? `Ce rôle est attribué à ${role.user_count} utilisateur(s). Retirez-le-leur d'abord : on ne supprime pas des droits sans le voir.`
              : 'Cette action est définitive.'}
          </DialogDescription>
        </DialogHeader>
        <ErrorAlert error={remove.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button variant="destructive" disabled={remove.isPending || role.user_count > 0} onClick={() => remove.mutate()}>
            {remove.isPending && <LoaderCircle className="animate-spin" />}
            Supprimer le rôle
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, KeyRound, LoaderCircle, Lock } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/copy-button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { generatePassword } from '@/lib/password'
import type { PermissionInfo, Role, UserCompanyAccess, UserInCompany } from '@/lib/types'
import { cn } from '@/lib/utils'
import { RolePicker } from '@/pages/admin/RolePicker'
import { groupByModule, moduleLabel, roleCovers, useCanGrant } from '@/pages/admin/roles'

interface Props {
  user: UserInCompany
  roles: Role[]
  canManage: boolean
  onClose: () => void
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 border-t pt-5 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  )
}

function Saved({ show, children = 'Enregistré' }: { show: boolean; children?: ReactNode }) {
  if (!show) return null
  return (
    <p className="flex items-center gap-1.5 text-sm text-emerald-700">
      <CheckCircle2 className="size-4" /> {children}
    </p>
  )
}

export function EditUserDialog({ user, roles, canManage, onClose }: Props) {
  const { me } = useAuth()
  const canGrant = useCanGrant()
  const isSelf = user.id === me?.user.id
  const isSuperuser = !!me?.user.is_superuser

  // Mêmes règles que l'API (qui reste seule juge) : on explique ici POURQUOI un
  // bloc est verrouillé, plutôt que de laisser l'utilisateur buter sur une erreur.
  const userRoles = roles.filter((r) => user.roles.some((ur) => ur.id === r.id))
  let lockReason: string | null = null
  if (!canManage) lockReason = "Vous n'avez pas le droit de modifier les utilisateurs."
  else if (!isSuperuser && user.is_superuser) lockReason = 'Seul un super-administrateur peut modifier ce compte.'
  else if (!isSuperuser && user.multi_company)
    lockReason =
      "Ce compte a aussi accès à d'autres sociétés : seul un super-administrateur peut modifier son identité et son mot de passe. Vous pouvez gérer ses rôles ici."
  else if (!isSuperuser && !userRoles.every(canGrant))
    lockReason = 'Ce compte a plus de droits que vous : vous ne pouvez pas le modifier.'

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {user.full_name}
            {user.is_superuser && <Badge variant="accent">Super-admin</Badge>}
            {!user.is_active && <Badge variant="outline">Désactivé</Badge>}
          </DialogTitle>
          <DialogDescription>{user.email}</DialogDescription>
        </DialogHeader>

        {lockReason && (
          <p className="flex gap-2 rounded-lg bg-secondary px-3 py-2 text-sm text-muted-foreground">
            <Lock className="mt-0.5 size-4 shrink-0" /> {lockReason}
          </p>
        )}

        <div className="space-y-5">
          <IdentitySection user={user} locked={!!lockReason} isSelf={isSelf} />
          <CompanyAccessSection user={user} roles={roles} isSelf={isSelf} />
          {canManage && (
            <Section title="Mot de passe">
              {isSelf ? (
                <p className="text-sm text-muted-foreground">
                  Pour changer votre propre mot de passe, passez par{' '}
                  <Link to="/profil" className="font-medium text-primary hover:underline">
                    votre profil
                  </Link>
                  .
                </p>
              ) : (
                <PasswordReset user={user} locked={!!lockReason} />
              )}
            </Section>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// --- Identité ---------------------------------------------------------------------------

const identitySchema = z.object({
  full_name: z.string().trim().min(1, 'Nom requis').max(150),
  email: z.email('Adresse e-mail invalide'),
  is_active: z.boolean(),
})

function IdentitySection({ user, locked, isSelf }: { user: UserInCompany; locked: boolean; isSelf: boolean }) {
  const queryClient = useQueryClient()
  const form = useForm({
    resolver: zodResolver(identitySchema),
    values: { full_name: user.full_name, email: user.email, is_active: user.is_active },
  })
  const save = useMutation({
    mutationFn: (v: z.infer<typeof identitySchema>) =>
      api<UserInCompany>(`/auth/users/${user.id}`, { method: 'PATCH', body: v }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      if (isSelf) void queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })
  const errors = form.formState.errors
  const active = useWatch({ control: form.control, name: 'is_active' })

  return (
    <Section title="Identité">
      <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="edit_full_name" label="Nom complet" error={errors.full_name?.message}>
            <Input id="edit_full_name" disabled={locked} {...form.register('full_name')} />
          </Field>
          <Field id="edit_email" label="Adresse e-mail" error={errors.email?.message}>
            <Input id="edit_email" type="email" disabled={locked} {...form.register('email')} />
          </Field>
        </div>
        <CheckRow
          checked={active}
          disabled={locked || isSelf}
          onChange={(on) => form.setValue('is_active', on, { shouldDirty: true })}
          title="Compte actif"
          description={
            isSelf
              ? 'Vous ne pouvez pas désactiver votre propre compte.'
              : 'Décoché : la personne ne peut plus se connecter et ses sessions ouvertes sont fermées. Rien n\'est supprimé (son nom reste dans l\'historique).'
          }
        />
        <ErrorAlert error={save.error} />
        {!locked && (
          <div className="flex items-center gap-4">
            <Button type="submit" disabled={save.isPending || !form.formState.isDirty}>
              {save.isPending && <LoaderCircle className="animate-spin" />}
              Enregistrer
            </Button>
            <Saved show={save.isSuccess && !form.formState.isDirty} />
          </div>
        )}
      </form>
    </Section>
  )
}

// --- Accès aux sociétés ----------------------------------------------------------------

function CompanyAccessSection({ user, roles, isSelf }: { user: UserInCompany; roles: Role[]; isSelf: boolean }) {
  const { company: current } = useAuth()
  const [editing, setEditing] = useState<number | null>(null)
  const access = useQuery({
    queryKey: ['user-access', user.id],
    queryFn: () => api<UserCompanyAccess[]>(`/org/user-access/${user.id}`, { withCompany: false }),
  })
  const catalog = useQuery({
    queryKey: ['permissions'],
    queryFn: () => api<PermissionInfo[]>('/auth/permissions', { withCompany: false }),
    staleTime: Infinity,
  })
  // Société courante en premier, puis celles où la personne a accès, puis les autres.
  const rows = [...(access.data ?? [])].sort(
    (x, y) =>
      Number(y.company.id === current?.id) - Number(x.company.id === current?.id) ||
      Number(y.roles.length > 0) - Number(x.roles.length > 0) ||
      x.company.name.localeCompare(y.company.name),
  )

  return (
    <Section title="Accès aux sociétés">
      <p className="text-sm text-muted-foreground">
        {isSelf
          ? 'Vous ne pouvez pas modifier vos propres accès.'
          : "Ses rôles dans chaque société, complétés si besoin par des droits individuels. Sans rôle, elle n'a pas accès à la société."}
      </p>
      <ErrorAlert error={access.error} />
      {access.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      <ul className="divide-y rounded-lg border">
        {rows.map((row) => (
          <CompanyAccessRow
            key={row.company.id}
            user={user}
            row={row}
            roles={roles}
            catalog={catalog.data ?? []}
            isCurrent={row.company.id === current?.id}
            editing={editing === row.company.id}
            onEdit={(on) => setEditing(on ? row.company.id : null)}
          />
        ))}
      </ul>
    </Section>
  )
}

function CompanyAccessRow({
  user,
  row,
  roles,
  catalog,
  isCurrent,
  editing,
  onEdit,
}: {
  user: UserInCompany
  row: UserCompanyAccess
  roles: Role[]
  catalog: PermissionInfo[]
  isCurrent: boolean
  editing: boolean
  onEdit: (on: boolean) => void
}) {
  const queryClient = useQueryClient()
  const initial = row.roles.map((r) => r.id)
  const [roleIds, setRoleIds] = useState<number[]>(initial)
  const [extras, setExtras] = useState<string[]>(row.extra_permissions)
  const hasAccess = row.roles.length > 0
  const sameSet = <T,>(x: T[], y: T[]) => x.length === y.length && x.every((v) => y.includes(v))
  const rolesDirty = !sameSet(roleIds, initial)
  const extrasDirty = !sameSet(extras, row.extra_permissions)
  const removing = hasAccess && roleIds.length === 0
  const dirty = rolesDirty || (roleIds.length > 0 && extrasDirty)
  const labels = new Map(catalog.map((p) => [p.code, p.label]))

  const save = useMutation({
    mutationFn: async () => {
      const base = `/auth/users/${user.id}/companies/${row.company.id}`
      // Les rôles d'abord : ils donnent l'accès sans lequel les droits individuels sont refusés.
      if (rolesDirty) await api<UserInCompany>(`${base}/roles`, { method: 'PUT', body: { role_ids: roleIds } })
      if (roleIds.length > 0 && extrasDirty)
        await api<string[]>(`${base}/permissions`, { method: 'PUT', body: { permissions: extras } })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['user-access', user.id] })
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      onEdit(false)
    },
  })

  return (
    <li className="space-y-3 p-3">
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold',
            hasAccess ? 'bg-accent/20 text-accent-foreground' : 'bg-secondary text-muted-foreground',
          )}
        >
          {row.company.code.slice(0, 2)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
            {row.company.name}
            {isCurrent && <Badge variant="secondary">courante</Badge>}
            {!row.company.is_active && <Badge variant="outline">désactivée</Badge>}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {hasAccess ? (
              <>
                {row.roles.map((r) => (
                  <Badge key={r.id} variant="secondary">
                    {r.name}
                  </Badge>
                ))}
                {row.extra_permissions.map((p) => (
                  <Badge key={p} variant="outline" title={`Droit individuel : ${p}`}>
                    + {labels.get(p) ?? p}
                  </Badge>
                ))}
              </>
            ) : (
              <span className="text-xs text-muted-foreground">Pas d'accès</span>
            )}
          </div>
        </div>
        {row.can_manage && !editing && (
          <Button
            type="button"
            size="sm"
            variant={hasAccess ? 'outline' : 'secondary'}
            onClick={() => {
              setRoleIds(initial)
              setExtras(row.extra_permissions)
              save.reset()
              onEdit(true)
            }}
          >
            {hasAccess ? 'Modifier' : "Donner l'accès"}
          </Button>
        )}
      </div>

      {editing && (
        <div className="space-y-3 rounded-lg bg-secondary/40 p-3">
          <RolePicker roles={roles} value={roleIds} onChange={setRoleIds} grantableIds={row.grantable_role_ids} />
          {roleIds.length > 0 && (
            <ExtraPermissions
              catalog={catalog}
              selectedRoles={roles.filter((r) => roleIds.includes(r.id))}
              value={extras}
              onChange={setExtras}
              grantable={row.grantable_permissions}
            />
          )}
          <ErrorAlert error={save.error} />
          {removing && (
            <p className="text-xs text-muted-foreground">
              Sans rôle, la personne n'aura plus accès à {row.company.name}. Son compte n'est pas supprimé.
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => onEdit(false)}>
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              variant={removing ? 'destructive' : 'default'}
              disabled={!dirty || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending && <LoaderCircle className="animate-spin" />}
              {removing ? "Retirer l'accès" : hasAccess ? 'Enregistrer' : "Donner l'accès"}
            </Button>
          </div>
        </div>
      )}
    </li>
  )
}

/** Droits individuels : ceux que les rôles cochés donnent déjà sont affichés, grisés. */
function ExtraPermissions({
  catalog,
  selectedRoles,
  value,
  onChange,
  grantable,
}: {
  catalog: PermissionInfo[]
  selectedRoles: Role[]
  value: string[]
  onChange: (permissions: string[]) => void
  grantable: string[]
}) {
  return (
    <details className="group rounded-lg border bg-card" open={value.length > 0}>
      <summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium select-none">
        <span className="inline-block transition-transform group-open:rotate-90">›</span> Droits supplémentaires
        {value.length > 0 && <span className="ml-1 text-muted-foreground">({value.length})</span>}
        <span className="block text-xs font-normal text-muted-foreground">
          En plus de ses rôles, pour cette personne seulement.
        </span>
      </summary>
      <div className="space-y-3 border-t p-3">
        {groupByModule(catalog).map(([module, perms]) => (
          <div key={module} className="space-y-1.5">
            <h5 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">{moduleLabel(module)}</h5>
            {perms.map((p) => {
              const via = selectedRoles.find((r) => roleCovers(r, p.code))
              const allowed = grantable.includes(p.code)
              return (
                <CheckRow
                  key={p.code}
                  checked={!!via || value.includes(p.code)}
                  disabled={!!via || !allowed}
                  onChange={(on) => onChange(on ? [...value, p.code] : value.filter((c) => c !== p.code))}
                  title={p.label}
                  description={
                    via
                      ? `Déjà donné par le rôle « ${via.name} »`
                      : allowed
                        ? <span className="font-mono">{p.code}</span>
                        : "Vous n'avez pas ce droit : vous ne pouvez pas l'accorder"
                  }
                />
              )
            })}
          </div>
        ))}
      </div>
    </details>
  )
}

// --- Mot de passe ---------------------------------------------------------------------

function PasswordReset({ user, locked }: { user: UserInCompany; locked: boolean }) {
  const [password, setPassword] = useState<string | null>(null)
  const reset = useMutation({
    mutationFn: (newPassword: string) =>
      api<void>(`/auth/users/${user.id}/password`, { method: 'POST', body: { new_password: newPassword } }),
  })

  if (locked) return <p className="text-sm text-muted-foreground">Réinitialisation non autorisée pour ce compte.</p>

  if (reset.isSuccess && password) {
    return (
      <div className="space-y-2">
        <Saved show>Mot de passe réinitialisé, ses sessions ont été fermées.</Saved>
        <div className="flex gap-2">
          <Input readOnly value={password} className="font-mono" aria-label="Nouveau mot de passe" />
          <CopyButton value={password} label="Copier le mot de passe" />
        </div>
        <p className="text-xs text-muted-foreground">
          Notez-le maintenant : il ne sera plus affiché. Transmettez-le par un canal sûr.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Génère un nouveau mot de passe provisoire et déconnecte {user.full_name} de tous ses appareils.
      </p>
      <ErrorAlert error={reset.error} />
      <Button
        type="button"
        variant="outline"
        disabled={reset.isPending}
        onClick={() => {
          const generated = generatePassword()
          setPassword(generated)
          reset.mutate(generated)
        }}
      >
        {reset.isPending ? <LoaderCircle className="animate-spin" /> : <KeyRound />}
        Réinitialiser le mot de passe
      </Button>
    </div>
  )
}

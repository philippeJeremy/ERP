import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Copy, KeyRound, LoaderCircle, Lock } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { generatePassword } from '@/lib/password'
import type { Role, UserInCompany } from '@/lib/types'
import { RolePicker } from '@/pages/admin/RolePicker'
import { useCanGrant } from '@/pages/admin/roles'

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
  const { me, company } = useAuth()
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
          <RolesSection user={user} roles={roles} locked={!canManage || isSelf} isSelf={isSelf} companyName={company?.name} onRemoved={onClose} />
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

// --- Rôles ------------------------------------------------------------------------------

function RolesSection({
  user,
  roles,
  locked,
  isSelf,
  companyName,
  onRemoved,
}: {
  user: UserInCompany
  roles: Role[]
  locked: boolean
  isSelf: boolean
  companyName?: string
  onRemoved: () => void
}) {
  const queryClient = useQueryClient()
  const initial = user.roles.map((r) => r.id)
  const [roleIds, setRoleIds] = useState<number[]>(initial)
  const dirty = roleIds.length !== initial.length || roleIds.some((id) => !initial.includes(id))
  const removing = roleIds.length === 0

  const save = useMutation({
    mutationFn: () =>
      api<UserInCompany>(`/auth/users/${user.id}/roles`, { method: 'PUT', body: { role_ids: roleIds } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
      if (removing) onRemoved()
    },
  })

  return (
    <Section title={`Rôles dans ${companyName ?? 'la société'}`}>
      {isSelf && <p className="text-sm text-muted-foreground">Vous ne pouvez pas modifier vos propres rôles.</p>}
      <RolePicker roles={roles} value={roleIds} onChange={setRoleIds} disabled={locked} />
      <ErrorAlert error={save.error} />
      {!locked && (
        <div className="flex flex-wrap items-center gap-4">
          <Button
            type="button"
            variant={removing ? 'destructive' : 'default'}
            disabled={save.isPending || !dirty}
            onClick={() => save.mutate()}
          >
            {save.isPending && <LoaderCircle className="animate-spin" />}
            {removing ? `Retirer l'accès à ${companyName ?? 'la société'}` : 'Enregistrer les rôles'}
          </Button>
          <Saved show={save.isSuccess && !dirty} />
          {removing && dirty && (
            <p className="basis-full text-xs text-muted-foreground">
              Sans rôle, la personne n'a plus accès à cette société. Son compte n'est pas supprimé.
            </p>
          )}
        </div>
      )}
    </Section>
  )
}

// --- Mot de passe ---------------------------------------------------------------------

function PasswordReset({ user, locked }: { user: UserInCompany; locked: boolean }) {
  const [password, setPassword] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
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
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Copier le mot de passe"
            title={copied ? 'Copié' : 'Copier'}
            onClick={async () => {
              await navigator.clipboard.writeText(password)
              setCopied(true)
            }}
          >
            <Copy />
          </Button>
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

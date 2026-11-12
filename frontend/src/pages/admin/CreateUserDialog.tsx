import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, LoaderCircle, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api, ApiError } from '@/lib/api'
import { generatePassword } from '@/lib/password'
import type { Role, UserInCompany } from '@/lib/types'
import { RolePicker } from '@/pages/admin/RolePicker'

const schema = z.object({
  full_name: z.string().trim().min(1, 'Nom requis').max(150),
  email: z.email('Adresse e-mail invalide'),
  password: z.string().min(12, '12 caractères minimum').max(128),
})
type Values = z.infer<typeof schema>

export function CreateUserDialog({ roles, onClose }: { roles: Role[]; onClose: () => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [roleIds, setRoleIds] = useState<number[]>([])
  const [copied, setCopied] = useState(false)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', email: '', password: generatePassword() },
  })

  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ['users'] })
    void queryClient.invalidateQueries({ queryKey: ['roles'] })
    onClose()
  }
  const create = useMutation({
    mutationFn: (v: Values) =>
      api<UserInCompany>('/auth/users', { method: 'POST', body: { ...v, role_ids: roleIds } }),
    onSuccess: done,
  })
  // Le compte existe déjà (créé dans une autre société) : on lui donne accès à celle-ci.
  const attach = useMutation({
    mutationFn: () =>
      api<UserInCompany>('/auth/users/attach', {
        method: 'POST',
        body: { email: form.getValues('email'), role_ids: roleIds },
      }),
    onSuccess: done,
  })
  const exists = create.error instanceof ApiError && create.error.code === 'compte_existant'
  const errors = form.formState.errors

  const copyPassword = async () => {
    await navigator.clipboard.writeText(form.getValues('password'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouvel utilisateur</DialogTitle>
          <DialogDescription>Il aura accès à {company?.name} avec les rôles choisis.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => create.mutate(v))} className="space-y-4" noValidate>
          <Field id="new_full_name" label="Nom complet" error={errors.full_name?.message}>
            <Input id="new_full_name" autoComplete="off" {...form.register('full_name')} />
          </Field>
          <Field id="new_email" label="Adresse e-mail" error={errors.email?.message} hint="Elle sert d'identifiant de connexion.">
            <Input id="new_email" type="email" autoComplete="off" {...form.register('email')} />
          </Field>
          <Field
            id="new_password"
            label="Mot de passe provisoire"
            error={errors.password?.message}
            hint="Transmettez-le par un canal sûr (pas par e-mail). L'utilisateur le changera dans son profil."
          >
            <div className="flex gap-2">
              <Input id="new_password" className="font-mono" autoComplete="off" {...form.register('password')} />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => form.setValue('password', generatePassword(), { shouldValidate: true })}
                aria-label="Générer un autre mot de passe"
                title="Générer un autre mot de passe"
              >
                <RefreshCw />
              </Button>
              <Button type="button" variant="outline" size="icon" onClick={copyPassword} aria-label="Copier le mot de passe" title={copied ? 'Copié' : 'Copier'}>
                <Copy />
              </Button>
            </div>
          </Field>

          <fieldset className="space-y-2">
            <legend className="mb-2 text-sm font-medium">Rôles</legend>
            <RolePicker roles={roles} value={roleIds} onChange={setRoleIds} />
          </fieldset>

          {exists ? (
            <Alert>
              <AlertDescription>
                <p>Un compte existe déjà avec cet e-mail (il a accès à une autre société). Vous pouvez lui donner accès à {company?.name} avec les rôles cochés : son nom et son mot de passe ne changent pas.</p>
                <Button type="button" size="sm" className="mt-3" disabled={attach.isPending || roleIds.length === 0} onClick={() => attach.mutate()}>
                  {attach.isPending && <LoaderCircle className="animate-spin" />}
                  Ajouter ce compte à la société
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            <ErrorAlert error={create.error} />
          )}
          <ErrorAlert error={attach.error} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={create.isPending || roleIds.length === 0}>
              {create.isPending && <LoaderCircle className="animate-spin" />}
              Créer l'utilisateur
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

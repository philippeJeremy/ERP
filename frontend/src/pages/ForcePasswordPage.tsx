import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, LoaderCircle, LogOut } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Navigate, useNavigate } from 'react-router'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Logo } from '@/components/layout/Logo'
import { Button } from '@/components/ui/button'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'

const schema = z
  .object({
    current_password: z.string().min(1, 'Mot de passe provisoire requis'),
    new_password: z.string().min(12, '12 caractères minimum').max(128),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, { path: ['confirm'], message: 'Les deux mots de passe diffèrent' })
  .refine((d) => d.new_password !== d.current_password, {
    path: ['new_password'],
    message: 'Choisissez un mot de passe différent du provisoire',
  })
type Values = z.infer<typeof schema>

/** Écran imposé tant que le mot de passe provisoire (donné par un administrateur) n'a pas été changé. */
export function ForcePasswordPage() {
  const { me, logout } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: '', new_password: '', confirm: '' },
  })
  const change = useMutation({
    mutationFn: ({ current_password, new_password }: Values) =>
      api<void>('/auth/me/password', { method: 'POST', body: { current_password, new_password }, withCompany: false }),
    onSuccess: async () => {
      // Tout ce qui avait été refusé (sociétés, profil…) est rechargé avec les nouveaux droits.
      await queryClient.invalidateQueries()
      navigate('/', { replace: true })
    },
  })
  const errors = form.formState.errors

  if (me && !me.user.must_change_password && !change.isSuccess) return <Navigate to="/" replace />

  return (
    <div className="flex min-h-svh items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm space-y-8">
        <Logo className="text-lg" />
        <div className="space-y-2">
          <span className="flex size-10 items-center justify-center rounded-lg bg-accent/20 text-accent-foreground">
            <KeyRound className="size-5" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight">Choisissez votre mot de passe</h1>
          <p className="text-sm text-muted-foreground">
            Bienvenue {me?.user.full_name.split(' ')[0]}. Le mot de passe qui vous a été transmis est provisoire :
            remplacez-le par un mot de passe que vous seul connaissez pour accéder à l'ERP.
          </p>
        </div>

        <form onSubmit={form.handleSubmit((v) => change.mutate(v))} className="space-y-5" noValidate>
          <Field id="current_password" label="Mot de passe provisoire" error={errors.current_password?.message}>
            <Input id="current_password" type="password" autoComplete="current-password" autoFocus {...form.register('current_password')} />
          </Field>
          <Field
            id="new_password"
            label="Nouveau mot de passe"
            error={errors.new_password?.message}
            hint="12 caractères minimum. Une phrase de plusieurs mots est sûre et facile à retenir."
          >
            <Input id="new_password" type="password" autoComplete="new-password" {...form.register('new_password')} />
          </Field>
          <Field id="confirm" label="Confirmation" error={errors.confirm?.message}>
            <Input id="confirm" type="password" autoComplete="new-password" {...form.register('confirm')} />
          </Field>
          <ErrorAlert error={change.error} />
          <Button type="submit" size="lg" className="w-full" disabled={change.isPending}>
            {change.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer et continuer
          </Button>
        </form>

        <button
          type="button"
          onClick={() => void logout()}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <LogOut className="size-3.5" /> Se déconnecter
        </button>
      </div>
    </div>
  )
}

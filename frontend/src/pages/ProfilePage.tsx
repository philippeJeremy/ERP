import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Building2, CheckCircle2, KeyRound, LoaderCircle, Monitor, ShieldCheck, Smartphone, UserRound } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/lib/api'
import { describeUserAgent, formatDateTime, formatRelative, initials } from '@/lib/format'
import type { SessionInfo, UserRead } from '@/lib/types'

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : 'Une erreur est survenue, réessayez.')

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

function Feedback({ success, error }: { success?: string | null; error?: unknown }) {
  if (error)
    return (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  if (success)
    return (
      <p className="flex items-center gap-1.5 text-sm text-emerald-700">
        <CheckCircle2 className="size-4" /> {success}
      </p>
    )
  return null
}

// --- Informations ---------------------------------------------------------------------

const profileSchema = z.object({ full_name: z.string().trim().min(1, 'Nom requis').max(150) })

function ProfileForm() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const form = useForm({ resolver: zodResolver(profileSchema), values: { full_name: me?.user.full_name ?? '' } })
  const mutation = useMutation({
    mutationFn: (data: z.infer<typeof profileSchema>) => api<UserRead>('/auth/me', { method: 'PATCH', body: data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserRound className="size-4 text-muted-foreground" /> Informations
        </CardTitle>
        <CardDescription>Votre nom apparaît dans l'historique des modifications.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit((d) => mutation.mutate(d))} className="space-y-4" noValidate>
          <Field id="full_name" label="Nom complet" error={form.formState.errors.full_name?.message}>
            <Input id="full_name" autoComplete="name" {...form.register('full_name')} />
          </Field>
          <Field id="email" label="Adresse e-mail">
            <Input id="email" value={me?.user.email ?? ''} disabled readOnly />
          </Field>
          <p className="-mt-2 text-xs text-muted-foreground">
            L'adresse e-mail sert d'identifiant : seul un administrateur peut la modifier.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={mutation.isPending || !form.formState.isDirty}>
              {mutation.isPending && <LoaderCircle className="animate-spin" />}
              Enregistrer
            </Button>
            <Feedback success={mutation.isSuccess && !form.formState.isDirty ? 'Enregistré' : null} error={mutation.error} />
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

// --- Mot de passe ---------------------------------------------------------------------

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Mot de passe actuel requis'),
    new_password: z.string().min(12, '12 caractères minimum').max(128),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, { path: ['confirm'], message: 'Les deux mots de passe diffèrent' })
  .refine((d) => d.new_password !== d.current_password, {
    path: ['new_password'],
    message: "Le nouveau mot de passe doit être différent de l'actuel",
  })

function PasswordForm() {
  const queryClient = useQueryClient()
  const [done, setDone] = useState(false)
  const form = useForm({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirm: '' },
  })
  const mutation = useMutation({
    mutationFn: ({ current_password, new_password }: z.infer<typeof passwordSchema>) =>
      api<void>('/auth/me/password', { method: 'POST', body: { current_password, new_password } }),
    onMutate: () => setDone(false),
    onSuccess: () => {
      form.reset()
      setDone(true)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
  const errors = form.formState.errors

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4 text-muted-foreground" /> Mot de passe
        </CardTitle>
        <CardDescription>Après le changement, vos autres sessions sont fermées.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit((d) => mutation.mutate(d))} className="space-y-4" noValidate>
          <Field id="current_password" label="Mot de passe actuel" error={errors.current_password?.message}>
            <Input id="current_password" type="password" autoComplete="current-password" {...form.register('current_password')} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="new_password" label="Nouveau mot de passe" error={errors.new_password?.message}>
              <Input id="new_password" type="password" autoComplete="new-password" {...form.register('new_password')} />
            </Field>
            <Field id="confirm" label="Confirmation" error={errors.confirm?.message}>
              <Input id="confirm" type="password" autoComplete="new-password" {...form.register('confirm')} />
            </Field>
          </div>
          <p className="text-xs text-muted-foreground">
            12 caractères minimum. Une phrase de passe (plusieurs mots) est plus sûre et plus facile à retenir.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending && <LoaderCircle className="animate-spin" />}
              Changer le mot de passe
            </Button>
            <Feedback success={done ? 'Mot de passe modifié, vos autres sessions ont été fermées.' : null} error={mutation.error} />
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

// --- Accès ------------------------------------------------------------------------------

function AccessCard() {
  const { me, companies } = useAuth()
  const names = new Map(companies.map((c) => [c.id, c]))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="size-4 text-muted-foreground" /> Mes accès
        </CardTitle>
        <CardDescription>Vos rôles dans chaque société.</CardDescription>
      </CardHeader>
      <CardContent>
        {me?.user.is_superuser && (
          <p className="mb-3 flex items-center gap-2 rounded-lg bg-accent/15 px-3 py-2 text-sm text-accent-foreground">
            <ShieldCheck className="size-4" /> Super-administrateur : tous les droits dans toutes les sociétés.
          </p>
        )}
        <ul className="divide-y">
          {me?.companies.map((access) => {
            const c = names.get(access.company_id)
            return (
              <li key={access.company_id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{c?.name ?? `Société #${access.company_id}`}</p>
                  <p className="text-xs text-muted-foreground">{c?.code}</p>
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  {access.roles.map((r) => (
                    <Badge key={r.id} variant="secondary">
                      {r.name}
                    </Badge>
                  ))}
                </div>
              </li>
            )
          })}
          {me?.companies.length === 0 && <li className="py-2 text-sm text-muted-foreground">Aucun rôle attribué.</li>}
        </ul>
      </CardContent>
    </Card>
  )
}

// --- Sessions -------------------------------------------------------------------------

function SessionsCard() {
  const queryClient = useQueryClient()
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: () => api<SessionInfo[]>('/auth/me/sessions', { withCompany: false }) })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['sessions'] })
  const revoke = useMutation({
    mutationFn: (id: string) => api<void>(`/auth/me/sessions/${id}`, { method: 'DELETE', withCompany: false }),
    onSuccess: refresh,
  })
  const revokeOthers = useMutation({
    mutationFn: () => api<void>('/auth/me/sessions/revoke-others', { method: 'POST', withCompany: false }),
    onSuccess: refresh,
  })
  const others = sessions.data?.filter((s) => !s.current).length ?? 0

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-start justify-between gap-3 sm:flex-row">
        <div className="grid gap-1">
          <CardTitle className="flex items-center gap-2">
            <Monitor className="size-4 text-muted-foreground" /> Sessions actives
          </CardTitle>
          <CardDescription>
            Les navigateurs connectés à votre compte. Fermez celles que vous ne reconnaissez pas.
          </CardDescription>
        </div>
        {others > 0 && (
          <Button variant="outline" size="sm" onClick={() => revokeOthers.mutate()} disabled={revokeOthers.isPending}>
            Déconnecter les autres sessions
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {sessions.isPending ? (
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <ul className="divide-y">
            {sessions.data?.map((s) => {
              const ua = describeUserAgent(s.user_agent)
              const Icon = ua.mobile ? Smartphone : Monitor
              return (
                <li key={s.id} className="flex items-center gap-4 py-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary">
                    <Icon className="size-4 text-muted-foreground" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {ua.browser}
                      {ua.os && ` · ${ua.os}`}
                      {s.current && <Badge variant="success">Cette session</Badge>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Connecté le {formatDateTime(s.started_at)} · actif {formatRelative(s.last_used_at)}
                    </p>
                  </div>
                  {!s.current && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => revoke.mutate(s.id)}
                      disabled={revoke.isPending}
                    >
                      Fermer
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

// --- Page -------------------------------------------------------------------------------

export function ProfilePage() {
  const { me } = useAuth()
  const user = me?.user

  return (
    <>
      <div className="mb-8 flex items-center gap-4">
        <span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground ring-4 ring-accent/30">
          {initials(user?.full_name)}
        </span>
        <PageHeaderInline name={user?.full_name} email={user?.email} superuser={user?.is_superuser} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <ProfileForm />
          <PasswordForm />
        </div>
        <div className="space-y-6 lg:col-span-2">
          <AccessCard />
        </div>
        <div className="lg:col-span-5">
          <SessionsCard />
        </div>
      </div>
    </>
  )
}

function PageHeaderInline({ name, email, superuser }: { name?: string; email?: string; superuser?: boolean }) {
  return (
    <div className="min-w-0 space-y-1">
      <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
        <span className="truncate">{name}</span>
        {superuser && <Badge variant="accent">Super-admin</Badge>}
      </h1>
      <p className="truncate text-sm text-muted-foreground">{email}</p>
    </div>
  )
}

import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Clock, Eye, EyeOff, LoaderCircle, Lock } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { useAuth } from '@/auth/useAuth'
import { Logo } from '@/components/layout/Logo'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/lib/api'

// Règles de validation du formulaire. Vérifiées dans le navigateur pour un retour
// immédiat ; l'API refait ses propres contrôles (ne jamais faire confiance au client).
const schema = z.object({
  email: z.email('Adresse e-mail invalide'),
  password: z.string().min(1, 'Mot de passe requis'),
})
type FormValues = z.infer<typeof schema>

/** Évite les redirections vers un autre site après connexion (« open redirect »). */
function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export function LoginPage() {
  const { status, sessionExpired, login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [showPassword, setShowPassword] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  const next = safeNext(params.get('next'))
  if (status === 'authenticated') return <Navigate to={next} replace />

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    try {
      await login(values.email, values.password)
      navigate(next, { replace: true })
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : 'Impossible de joindre le serveur. Vérifiez votre connexion VPN.',
      )
    }
  }

  return (
    <div className="grid min-h-svh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* Panneau de marque (masqué sur mobile) */}
      <aside className="relative hidden overflow-hidden bg-[oklch(0.22_0.03_255)] p-10 text-white lg:flex lg:flex-col">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
        <Logo inverted className="relative text-lg" />
        <div className="relative mt-auto max-w-sm space-y-4">
          <div className="h-1 w-10 rounded-full bg-accent" />
          <h2 className="text-3xl leading-tight font-semibold text-balance">
            Ventes, achats, stocks et facturation, pour toutes vos sociétés.
          </h2>
          <p className="text-sm text-white/60">
            Chaque entité garde sa numérotation, ses comptes et ses droits d'accès.
          </p>
        </div>
        <p className="relative mt-10 flex items-center gap-2 text-xs text-white/40">
          <Lock className="size-3.5" /> Accès réservé au réseau privé de l'entreprise
        </p>
      </aside>

      {/* Formulaire */}
      <main className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-8">
          <Logo className="text-lg lg:hidden" />
          <div className="space-y-1.5">
            <h1 className="text-2xl font-semibold tracking-tight">Connexion</h1>
            <p className="text-sm text-muted-foreground">Utilisez votre adresse e-mail professionnelle.</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
            {sessionExpired && !serverError && (
              <Alert>
                <Clock />
                <AlertDescription>
                  Votre session a expiré (inactivité ou durée maximale atteinte). Reconnectez-vous pour continuer.
                </AlertDescription>
              </Alert>
            )}
            {serverError && (
              <Alert variant="destructive">
                <AlertCircle />
                <AlertDescription>{serverError}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Adresse e-mail</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                autoFocus
                placeholder="prenom.nom@entreprise.fr"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? 'email-error' : undefined}
                {...register('email')}
              />
              {errors.email && (
                <p id="email-error" className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Mot de passe</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  className="pr-10"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'password-error' : undefined}
                  {...register('password')}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
              {isSubmitting && <LoaderCircle className="animate-spin" />}
              Se connecter
            </Button>
          </form>

          <p className="text-xs text-muted-foreground">
            Mot de passe oublié ? Contactez l'administrateur de votre société.
          </p>
        </div>
      </main>
    </div>
  )
}

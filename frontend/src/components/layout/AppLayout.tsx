import { Building2, LogOut } from 'lucide-react'
import { Outlet } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Logo } from '@/components/layout/Logo'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Cadre des pages connectées : barre du haut (société, utilisateur) + contenu. */
export function AppLayout() {
  const { me, companies, company, selectCompany, logout } = useAuth()

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo />
          <div className="h-6 w-px bg-border" />

          {/* Sélecteur de société : change l'en-tête X-Company-Id de toutes les requêtes. */}
          {companies.length > 0 && (
            <label className="flex items-center gap-2 text-sm">
              <Building2 className="size-4 text-muted-foreground" aria-hidden />
              <span className="sr-only">Société</span>
              <select
                value={company?.id ?? ''}
                onChange={(e) => selectCompany(Number(e.target.value))}
                disabled={companies.length === 1}
                className="h-8 max-w-56 truncate rounded-md border border-input bg-card px-2 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:appearance-none disabled:border-transparent disabled:opacity-100"
              >
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right text-sm leading-tight sm:block">
              <div className="font-medium">{me?.user.full_name}</div>
              <div className="text-xs text-muted-foreground">{me?.user.email}</div>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Se déconnecter" title="Se déconnecter">
              <LogOut />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {company ? (
          <Outlet />
        ) : (
          <Card className="mx-auto max-w-md">
            <CardHeader>
              <CardTitle>Aucune société accessible</CardTitle>
              <CardDescription>
                Votre compte n'a encore accès à aucune société. Demandez à un administrateur de vous attribuer un rôle.
              </CardDescription>
            </CardHeader>
          </Card>
        )}
      </main>
    </div>
  )
}

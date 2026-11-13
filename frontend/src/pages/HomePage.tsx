import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Building2, Server, UserRound } from 'lucide-react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { NAVIGATION } from '@/components/layout/nav'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime, initials } from '@/lib/format'
import { can } from '@/lib/permissions'

const DESCRIPTIONS: Record<string, string> = {
  Fournisseurs: 'Référentiel fournisseurs : adresses, contacts, conditions d’achat et banque.',
  Articles: 'Pneus, pièces et accessoires ; prix d’achat et imports des tarifs fournisseurs.',
  Clients: 'Fiches clients, adresses de facturation et de livraison, conditions de vente.',
  Ventes: 'Devis, commandes clients et suivi des livraisons.',
  Achats: 'Commandes fournisseurs et réceptions.',
  Stock: 'Entrepôts, emplacements et mouvements de stock.',
  Facturation: 'Factures, avoirs et règlements, numérotés par société.',
}

const today = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate text-right font-medium">{value || '—'}</dd>
    </div>
  )
}

export function HomePage() {
  const { me, company } = useAuth()
  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await (await fetch('/api/health')).json()) as { version: string },
  })

  const roles = me?.companies.find((c) => c.company_id === company?.id)?.roles ?? []
  const roleLabel = me?.user.is_superuser ? 'Super-administrateur' : roles.map((r) => r.name).join(', ')
  const modules = NAVIGATION.find((s) => s.title === 'Gestion')?.items ?? []

  return (
    <>
      <PageHeader
        title={
          <>
            <span className="mb-1 block text-sm font-normal text-muted-foreground first-letter:uppercase">{today}</span>
            Bonjour {me?.user.full_name.split(' ')[0]}
          </>
        }
        description={[company?.name, roleLabel].filter(Boolean).join(' · ')}
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Modules</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((m) => {
            const Icon = m.icon
            const open = !m.soon && (!m.permission || can(me?.permissions, m.permission))
            const content = (
              <>
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
                  <Icon className="size-5" />
                </span>
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{m.label}</span>
                    {m.soon && <Badge variant="accent">bientôt</Badge>}
                    {open && (
                      <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">{DESCRIPTIONS[m.label]}</p>
                </div>
              </>
            )
            const className = 'group relative flex gap-4 rounded-xl border bg-card p-4 shadow-xs transition-colors'
            return open ? (
              <Link key={m.to} to={m.to} className={`${className} hover:border-primary/40 hover:bg-secondary/40`}>
                {content}
              </Link>
            ) : (
              <div key={m.to} className={className}>
                {content}
              </div>
            )
          })}
        </div>
      </section>

      <section className="mt-10 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <UserRound className="size-4 text-muted-foreground" /> Mon compte
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {initials(me?.user.full_name)}
              </span>
              <div className="min-w-0">
                <p className="truncate font-medium">{me?.user.full_name}</p>
                <p className="truncate text-sm text-muted-foreground">{me?.user.email}</p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Connecté depuis le {me?.user.last_login_at ? formatDateTime(me.user.last_login_at) : '—'}
            </p>
            <Link to="/profil" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
              Gérer mon profil <ArrowRight className="size-3.5" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Building2 className="size-4 text-muted-foreground" /> Société courante
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="divide-y">
              <Row label="Raison sociale" value={company?.name} />
              <Row label="Code" value={company?.code} />
              <Row label="SIREN" value={company?.siren} />
              <Row label="Devise" value={company?.currency} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Server className="size-4 text-muted-foreground" /> Système
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="divide-y">
              <Row label="Interface" value={import.meta.env.VITE_APP_VERSION ?? 'dev'} />
              <Row label="API" value={health.data?.version} />
              <Row label="Déconnexion après" value={me ? `${me.session_idle_minutes} min d'inactivité` : undefined} />
            </dl>
          </CardContent>
        </Card>
      </section>
    </>
  )
}

import { useQuery } from '@tanstack/react-query'
import { Building2, KeyRound, Server } from 'lucide-react'

import { useAuth } from '@/auth/useAuth'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{value || '—'}</dd>
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
  const firstName = me?.user.full_name.split(' ')[0]

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Bonjour {firstName}</h1>
        <p className="text-sm text-muted-foreground">Les modules métier arrivent bientôt ici.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="size-4 text-muted-foreground" /> Société courante
            </CardTitle>
            <CardDescription>{company?.code}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="divide-y">
              <Row label="Raison sociale" value={company?.name} />
              <Row label="SIREN" value={company?.siren} />
              <Row label="Ville" value={company?.city} />
              <Row label="Devise" value={company?.currency} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4 text-muted-foreground" /> Vos droits
            </CardTitle>
            <CardDescription>
              {me?.user.is_superuser ? 'Super-administrateur' : roles.map((r) => r.name).join(', ') || 'Aucun rôle'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-wrap gap-1.5">
              {me?.permissions.map((p) => (
                <li key={p} className="rounded-md bg-secondary px-2 py-0.5 font-mono text-xs">
                  {p === '*' ? 'tous les droits' : p}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="size-4 text-muted-foreground" /> Système
            </CardTitle>
            <CardDescription>Versions déployées</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="divide-y">
              <Row label="Interface" value={import.meta.env.VITE_APP_VERSION ?? 'dev'} />
              <Row label="API" value={health.data?.version} />
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

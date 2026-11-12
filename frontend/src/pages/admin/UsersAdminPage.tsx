import { ShieldCheck, Users } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { RolesTab } from '@/pages/admin/RolesTab'
import { UsersTab } from '@/pages/admin/UsersTab'

const TABS = [
  { id: 'utilisateurs', label: 'Utilisateurs', icon: Users },
  { id: 'roles', label: 'Rôles et droits', icon: ShieldCheck },
] as const

export function UsersAdminPage() {
  const { me, company } = useAuth()
  // L'onglet est dans l'URL (?onglet=roles) : on peut partager le lien ou recharger la page.
  const [params, setParams] = useSearchParams()
  const tab = params.get('onglet') === 'roles' ? 'roles' : 'utilisateurs'

  if (!can(me?.permissions, 'auth:read')) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir les utilisateurs de cette société.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <>
      <PageHeader
        title="Utilisateurs et rôles"
        description={`Qui a accès à ${company?.name}, et avec quels droits.`}
      />
      <div role="tablist" className="mb-6 flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setParams(t.id === 'roles' ? { onglet: 'roles' } : {}, { replace: true })}
            className={cn(
              '-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              tab === t.id
                ? 'border-accent text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <t.icon className="size-4" />
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'roles' ? <RolesTab /> : <UsersTab />}
    </>
  )
}

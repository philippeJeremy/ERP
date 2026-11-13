import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/auth/useAuth'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { CountsTab } from '@/pages/inventory/CountsTab'
import { MovesTab } from '@/pages/inventory/MovesTab'
import { StockTab } from '@/pages/inventory/StockTab'
import { TransfersTab } from '@/pages/inventory/TransfersTab'

const TABS = [
  { id: 'etat', label: 'État du stock' },
  { id: 'mouvements', label: 'Mouvements' },
  { id: 'transferts', label: 'Transferts' },
  { id: 'inventaires', label: 'Inventaires' },
] as const

export function StockPage() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const tab = TABS.find((t) => t.id === params.get('vue'))?.id ?? 'etat'
  if (!can(me?.permissions, 'inventory:read')) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir le stock.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <PageHeader title="Stock" description={`Le stock de ${company?.name} par dépôt, emplacement et DOT, valorisé au coût moyen pondéré.`} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            // On ne garde aucun filtre d'un onglet à l'autre.
            onClick={() => update(Object.fromEntries([...params.keys()].map((k) => [k, null]).concat([['vue', t.id === 'etat' ? null : t.id]])))}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'etat' && <StockTab />}
      {tab === 'mouvements' && <MovesTab />}
      {tab === 'transferts' && <TransfersTab />}
      {tab === 'inventaires' && <CountsTab />}
    </>
  )
}

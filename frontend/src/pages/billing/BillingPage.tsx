import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { AccountingTab } from '@/pages/billing/AccountingTab'
import { InvoicesTab } from '@/pages/billing/InvoicesTab'
import { PaymentsTab } from '@/pages/billing/PaymentsTab'
import { ReceivablesTab } from '@/pages/billing/ReceivablesTab'
import { SupplierInvoicesTab } from '@/pages/billing/SupplierInvoicesTab'
import { ToInvoiceTab } from '@/pages/billing/ToInvoiceTab'

const TABS = [
  { id: 'a_facturer', label: 'À facturer' },
  { id: 'factures', label: 'Factures et avoirs' },
  { id: 'reglements', label: 'Règlements' },
  { id: 'echeancier', label: 'Échéancier' },
  { id: 'fournisseurs', label: 'Factures fournisseur' },
  { id: 'comptabilite', label: 'Comptabilité', permission: 'billing:accounting' },
] as const

export function BillingPage() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const tabs = TABS.filter((t) => !('permission' in t) || can(me?.permissions, t.permission))
  const tab = tabs.find((t) => t.id === params.get('vue'))?.id ?? 'a_facturer'
  if (!can(me?.permissions, 'billing:read')) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir la facturation.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <PageHeader title="Facturation" description={`Factures, avoirs, règlements et factures fournisseur de ${company?.name}.`} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => update(Object.fromEntries([...params.keys()].map((k) => [k, null]).concat([['vue', t.id === 'a_facturer' ? null : t.id]])))}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'a_facturer' && <ToInvoiceTab />}
      {tab === 'factures' && <InvoicesTab />}
      {tab === 'reglements' && <PaymentsTab />}
      {tab === 'echeancier' && <ReceivablesTab />}
      {tab === 'fournisseurs' && <SupplierInvoicesTab />}
      {tab === 'comptabilite' && <AccountingTab />}
    </>
  )
}

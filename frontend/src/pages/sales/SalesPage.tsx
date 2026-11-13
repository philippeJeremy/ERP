import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { FileText, LoaderCircle, Plus, Search, ShoppingCart } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { fmtMoney } from '@/pages/inventory/types'
import { NewSalesDocDialog } from '@/pages/sales/NewSalesDocDialog'
import { PricesTab } from '@/pages/sales/PricesTab'
import { fmtDate, ORDER_STATUSES, QUOTE_STATUSES, type OrderListItem, type QuoteListItem } from '@/pages/sales/types'

const TABS = [
  { id: 'devis', label: 'Devis' },
  { id: 'commandes', label: 'Commandes client' },
  { id: 'tarif', label: 'Tarif de vente' },
] as const
const PAGE_SIZE = 25

export function SalesPage() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const tab = TABS.find((t) => t.id === params.get('vue'))?.id ?? 'devis'
  if (!can(me?.permissions, 'sales:read')) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir les ventes.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <PageHeader title="Ventes" description={`Devis, commandes client et tarif de ${company?.name}.`} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => update(Object.fromEntries([...params.keys()].map((k) => [k, null]).concat([['vue', t.id === 'devis' ? null : t.id]])))}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'devis' && <DocsList kind="quote" />}
      {tab === 'commandes' && <DocsList kind="order" />}
      {tab === 'tarif' && <PricesTab />}
    </>
  )
}

function DocsList({ kind }: { kind: 'quote' | 'order' }) {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const status = params.get('statut') ?? (kind === 'order' ? 'en_cours' : '')
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (status === 'en_cours') query.set('open', 'true')
  else if (status) query.set('status', status)
  if (q) query.set('q', q)
  const path = kind === 'quote' ? '/sales/quotes' : '/sales/orders'
  const list = useQuery({
    queryKey: [kind === 'quote' ? 'quotes' : 'orders', company?.id, query.toString()],
    queryFn: () => api<{ items: (QuoteListItem | OrderListItem)[]; total: number }>(`${path}?${query}`),
    placeholderData: keepPreviousData,
  })
  const statuses = kind === 'quote' ? QUOTE_STATUSES : ORDER_STATUSES
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher" placeholder="N°, client, référence client…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Statut" className="w-48" value={status} onChange={(e) => update({ statut: e.target.value || (kind === 'order' ? 'tous' : null), page: null })}>
          {kind === 'order' && <option value="en_cours">En cours</option>}
          <option value={kind === 'order' ? 'tous' : ''}>Tous les statuts</option>
          {Object.entries(statuses).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {can(me?.permissions, 'sales:manage') && (
          <Button className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> {kind === 'quote' ? 'Nouveau devis' : 'Nouvelle commande'}
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N°</th>
              <th className="px-4 py-2.5 font-medium">Client</th>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">{kind === 'quote' ? 'Validité' : 'Dépôt'}</th>
              <th className="px-4 py-2.5 text-right font-medium">Total TTC</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((x) => {
              const quote = kind === 'quote' ? (x as QuoteListItem) : null
              const order = kind === 'order' ? (x as OrderListItem) : null
              const st = statuses[x.status as keyof typeof statuses]
              return (
                <tr key={x.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(quote ? `/ventes/devis/${x.id}` : `/ventes/commandes/${x.id}`)}>
                  <td className="px-4 py-3 font-mono text-xs">{x.number}</td>
                  <td className="px-4 py-3 font-medium">{x.customer_name}</td>
                  <td className="px-4 py-3">{fmtDate(quote ? quote.quote_date : order!.order_date)}</td>
                  <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{quote ? fmtDate(quote.valid_until) : order!.site_name}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">{fmtMoney(x.total_ttc)}</td>
                  <td className="px-4 py-3">
                    <Badge variant={st.variant}>{st.label}</Badge>
                    {quote?.expired && (
                      <Badge variant="destructive" className="ml-1">
                        Expiré
                      </Badge>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            {kind === 'quote' ? <FileText className="size-8 text-muted-foreground/60" /> : <ShoppingCart className="size-8 text-muted-foreground/60" />}
            <p className="font-medium">{kind === 'quote' ? 'Aucun devis' : 'Aucune commande'}</p>
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={list.data?.total ?? 0}
        noun={kind === 'quote' ? ['devis', 'devis'] : ['commande', 'commandes']}
        onPage={(p) => update({ page: p ? String(p + 1) : null })}
      />
      {creating && <NewSalesDocDialog kind={kind} onClose={() => setCreating(false)} onCreated={(to) => navigate(to)} />}
    </>
  )
}

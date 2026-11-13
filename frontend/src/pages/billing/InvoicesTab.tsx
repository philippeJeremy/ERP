import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { LoaderCircle, Plus, ReceiptText, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { NewFreeInvoiceDialog } from '@/pages/billing/dialogs'
import { statusOf, type InvoiceListItem } from '@/pages/billing/types'
import { fmtMoney } from '@/pages/inventory/types'
import { fmtDate } from '@/pages/sales/types'

const PAGE_SIZE = 25

export function InvoicesTab() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const kind = params.get('type') ?? ''
  const status = params.get('statut') ?? ''
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (kind) query.set('kind', kind)
  if (status === 'brouillon') query.set('status', 'brouillon')
  else if (status) query.set('payment', status)
  if (q) query.set('q', q)
  const list = useQuery({
    queryKey: ['invoices', company?.id, query.toString()],
    queryFn: () => api<{ items: InvoiceListItem[]; total: number; total_ttc: string; total_balance: string }>(`/billing/invoices?${query}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher une facture" placeholder="N°, client…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Type" className="w-36" value={kind} onChange={(e) => update({ type: e.target.value, page: null })}>
          <option value="">Factures et avoirs</option>
          <option value="facture">Factures</option>
          <option value="avoir">Avoirs</option>
        </NativeSelect>
        <NativeSelect aria-label="Statut" className="w-44" value={status} onChange={(e) => update({ statut: e.target.value, page: null })}>
          <option value="">Tous les statuts</option>
          <option value="brouillon">Brouillons</option>
          <option value="a_payer">À payer</option>
          <option value="en_retard">En retard</option>
          <option value="payee">Payées</option>
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {can(me?.permissions, 'billing:manage') && (
          <Button variant="outline" className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> Facture libre
          </Button>
        )}
      </div>
      {list.data && list.data.total > 0 && (
        <p className="mb-3 text-sm text-muted-foreground">
          {list.data.total} document{list.data.total > 1 ? 's' : ''} · {fmtMoney(list.data.total_ttc)} TTC · reste dû <b className="text-foreground">{fmtMoney(list.data.total_balance)}</b>
        </p>
      )}
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N°</th>
              <th className="px-4 py-2.5 font-medium">Client</th>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Échéance</th>
              <th className="px-4 py-2.5 text-right font-medium">TTC</th>
              <th className="px-4 py-2.5 text-right font-medium">Reste dû</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((x) => {
              const st = statusOf(x.kind, x.payment_status)
              return (
                <tr key={x.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/facturation/factures/${x.id}`)}>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs">{x.number ?? 'Brouillon'}</span>
                    {x.kind === 'avoir' && (
                      <Badge variant="outline" className="ml-2">
                        Avoir
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 font-medium">{x.customer_name}</td>
                  <td className="px-4 py-3">{fmtDate(x.issue_date)}</td>
                  <td className={cn('hidden px-4 py-3 md:table-cell', x.days_late > 0 && 'font-medium text-destructive')}>
                    {x.kind === 'facture' ? fmtDate(x.due_date) : ''}
                    {x.days_late > 0 && ` (+${x.days_late} j)`}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(x.total_ttc)}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">{x.status === 'emise' && Number(x.balance) ? fmtMoney(x.balance) : ''}</td>
                  <td className="px-4 py-3">
                    <Badge variant={st.variant}>{st.label}</Badge>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <ReceiptText className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucune facture</p>
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['document', 'documents']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <NewFreeInvoiceDialog onClose={() => setCreating(false)} onCreated={(id) => navigate(`/facturation/factures/${id}`)} />}
    </>
  )
}

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { PaymentDialog } from '@/pages/billing/dialogs'
import { PAYMENT_METHODS, type Payment } from '@/pages/billing/types'
import { fmtMoney } from '@/pages/inventory/types'
import { fmtDate } from '@/pages/sales/types'

const PAGE_SIZE = 25

export function PaymentsTab() {
  const { me, company } = useAuth()
  const queryClient = useQueryClient()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const unallocated = params.get('non_lettres') === '1'
  const canPay = can(me?.permissions, 'billing:payments')
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (unallocated) query.set('unallocated', 'true')
  const list = useQuery({
    queryKey: ['payments', company?.id, query.toString()],
    queryFn: () => api<{ items: Payment[]; total: number }>(`/billing/payments?${query}`),
    placeholderData: keepPreviousData,
  })
  const refresh = () => {
    for (const k of ['payments', 'invoices', 'invoice', 'customer-account', 'receivables']) void queryClient.invalidateQueries({ queryKey: [k] })
  }
  const remove = useMutation({ mutationFn: (p: Payment) => api<void>(`/billing/payments/${p.id}`, { method: 'DELETE' }), onSuccess: refresh })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unallocated} onChange={(e) => update({ non_lettres: e.target.checked ? '1' : null, page: null })} />
          Non lettrés seulement (crédit client à affecter)
        </label>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {canPay && (
          <Button className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> Encaisser un règlement
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error ?? remove.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N°</th>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="px-4 py-2.5 font-medium">Client</th>
              <th className="px-4 py-2.5 font-medium">Mode</th>
              <th className="px-4 py-2.5 text-right font-medium">Montant</th>
              <th className="px-4 py-2.5 font-medium">Lettré sur</th>
              {canPay && <th className="w-12" />}
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((p) => (
              <tr key={p.id}>
                <td className="px-4 py-3 font-mono text-xs">{p.number}</td>
                <td className="px-4 py-3">{fmtDate(p.paid_on)}</td>
                <td className="px-4 py-3">
                  <Link to={`/clients/${p.customer_id}`} className="font-medium hover:underline">
                    {p.customer_name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  {PAYMENT_METHODS[p.method]}
                  {p.reference && <span className="block text-xs text-muted-foreground">{p.reference}</span>}
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums">{fmtMoney(p.amount)}</td>
                <td className="px-4 py-3 text-xs">
                  {p.allocations.map((a) => (
                    <Link key={a.id} to={`/facturation/factures/${a.invoice_id}`} className="mr-2 font-mono hover:underline">
                      {a.invoice_number} ({fmtMoney(a.amount)})
                    </Link>
                  ))}
                  {Number(p.unallocated) > 0 && <Badge variant="accent">{fmtMoney(p.unallocated)} non lettré</Badge>}
                </td>
                {canPay && (
                  <td className="px-2 py-1.5">
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label={`Supprimer ${p.number}`} onClick={() => window.confirm(`Supprimer le règlement ${p.number} ? Son lettrage sera défait.`) && remove.mutate(p)}>
                      <Trash2 />
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <Banknote className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun règlement</p>
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['règlement', 'règlements']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <PaymentDialog onDone={refresh} onClose={() => setCreating(false)} />}
    </>
  )
}

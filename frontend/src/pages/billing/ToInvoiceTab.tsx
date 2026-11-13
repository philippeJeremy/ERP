import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileCheck2, LoaderCircle, ReceiptText } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { fmtMoney } from '@/pages/inventory/types'
import type { CustomerToBill, Invoice } from '@/pages/billing/types'
import { fmtDate } from '@/pages/sales/types'

/** Les bons de livraison pas encore facturés : on coche, puis une facture par BL ou une
 * facture récapitulative par client. */
export function ToInvoiceTab() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'billing:manage')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const list = useQuery({ queryKey: ['to-invoice', company?.id], queryFn: () => api<CustomerToBill[]>('/billing/to-invoice') })
  const create = useMutation({
    mutationFn: (grouping: 'recap' | 'par_bl') => api<Invoice[]>('/billing/invoices/from-deliveries', { method: 'POST', body: { delivery_ids: [...selected], grouping } }),
    onSuccess: (invoices) => {
      setSelected(new Set())
      void queryClient.invalidateQueries({ queryKey: ['to-invoice'] })
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      if (invoices.length === 1) navigate(`/facturation/factures/${invoices[0].id}`)
      else navigate('/facturation?vue=factures&statut=brouillon')
    },
  })
  const toggle = (ids: number[], on: boolean) => {
    const next = new Set(selected)
    for (const id of ids) {
      if (on) next.add(id)
      else next.delete(id)
    }
    setSelected(next)
  }
  const total = (list.data ?? []).flatMap((c) => c.deliveries).filter((d) => selected.has(d.id)).reduce((s, d) => s + Number(d.total_ht), 0)
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <p className="flex-1 text-sm text-muted-foreground">
          Cochez les bons de livraison à facturer. « Facture récapitulative » regroupe tous les BL cochés d'un même client sur une seule facture (relevé mensuel).
        </p>
        {canManage && (
          <>
            <Button variant="outline" disabled={!selected.size || create.isPending} onClick={() => create.mutate('par_bl')}>
              Une facture par BL
            </Button>
            <Button disabled={!selected.size || create.isPending} onClick={() => create.mutate('recap')}>
              {create.isPending ? <LoaderCircle className="animate-spin" /> : <ReceiptText />}
              Facture récapitulative
            </Button>
          </>
        )}
      </div>
      {selected.size > 0 && (
        <p className="mb-3 text-sm">
          {selected.size} BL sélectionné{selected.size > 1 ? 's' : ''} · <b>{fmtMoney(total)}</b> HT
        </p>
      )}
      <ErrorAlert error={list.error ?? create.error} />
      {list.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {list.data?.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border bg-card py-12 text-center shadow-xs">
          <FileCheck2 className="size-8 text-muted-foreground/60" />
          <p className="font-medium">Tout est facturé</p>
          <p className="text-sm text-muted-foreground">Les livraisons validées apparaîtront ici.</p>
        </div>
      )}
      <div className="space-y-4">
        {list.data?.map((c) => {
          const ids = c.deliveries.map((d) => d.id)
          const all = ids.every((id) => selected.has(id))
          return (
            <div key={c.customer_id} className="overflow-hidden rounded-xl border bg-card shadow-xs">
              <div className="flex items-center gap-3 border-b bg-secondary/40 px-4 py-2.5">
                <input type="checkbox" aria-label={`Tout cocher ${c.customer_name}`} checked={all} onChange={(e) => toggle(ids, e.target.checked)} />
                <Link to={`/clients/${c.customer_id}`} className="font-medium hover:underline">
                  {c.customer_name}
                </Link>
                <span className="font-mono text-xs text-muted-foreground">{c.customer_code}</span>
                <span className="ml-auto text-sm tabular-nums">{fmtMoney(c.total_ht)} HT</span>
              </div>
              <table className="w-full text-sm">
                <tbody className="divide-y">
                  {c.deliveries.map((d) => (
                    <tr key={d.id}>
                      <td className="w-10 px-4 py-2">
                        <input type="checkbox" aria-label={`Facturer ${d.number}`} checked={selected.has(d.id)} onChange={(e) => toggle([d.id], e.target.checked)} />
                      </td>
                      <td className="px-2 py-2 font-mono text-xs">{d.number}</td>
                      <td className="px-2 py-2">{fmtDate(d.delivered_on)}</td>
                      <td className="px-2 py-2">
                        <Link to={`/ventes/commandes/${d.order_id}`} className="font-mono text-xs hover:underline">
                          {d.order_number}
                        </Link>
                        {d.customer_reference && <span className="ml-2 text-xs text-muted-foreground">réf. {d.customer_reference}</span>}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{fmtMoney(d.total_ht)} HT</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    </>
  )
}

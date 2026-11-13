import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileWarning, LoaderCircle, Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { PartnerPicker } from '@/pages/billing/dialogs'
import { SUPPLIER_STATUSES, toDec, type SupplierInvoice, type SupplierInvoiceListItem } from '@/pages/billing/types'
import { fmtMoney } from '@/pages/inventory/types'
import { fmtDate, today } from '@/pages/sales/types'

const PAGE_SIZE = 25
const AMOUNT = /^\d{1,12}([.,]\d{1,2})?$/

export function SupplierInvoicesTab() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const status = params.get('statut') ?? ''
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (status === 'a_payer') query.set('unpaid', 'true')
  else if (status) query.set('status', status)
  if (q) query.set('q', q)
  const list = useQuery({
    queryKey: ['supplier-invoices', company?.id, query.toString()],
    queryFn: () => api<{ items: SupplierInvoiceListItem[]; total: number }>(`/billing/supplier-invoices?${query}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher une facture fournisseur" placeholder="N°, fournisseur…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Statut" className="w-44" value={status} onChange={(e) => update({ statut: e.target.value, page: null })}>
          <option value="">Tous les statuts</option>
          <option value="brouillon">À contrôler</option>
          <option value="a_payer">Bon à payer, non payées</option>
          <option value="annulee">Annulées</option>
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {can(me?.permissions, 'billing:suppliers') && (
          <Button className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> Saisir une facture
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N° interne</th>
              <th className="px-4 py-2.5 font-medium">Fournisseur</th>
              <th className="px-4 py-2.5 font-medium">N° facture</th>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Échéance</th>
              <th className="px-4 py-2.5 text-right font-medium">TTC</th>
              <th className="px-4 py-2.5 text-right font-medium">Reste</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((x) => (
              <tr key={x.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/facturation/fournisseurs/${x.id}`)}>
                <td className="px-4 py-3 font-mono text-xs">{x.number}</td>
                <td className="px-4 py-3 font-medium">{x.partner_name}</td>
                <td className="px-4 py-3 font-mono text-xs">{x.supplier_number}</td>
                <td className="px-4 py-3">{fmtDate(x.invoice_date)}</td>
                <td className="hidden px-4 py-3 md:table-cell">{fmtDate(x.due_date)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(x.total_ttc)}</td>
                <td className="px-4 py-3 text-right font-medium tabular-nums">{x.status === 'bon_a_payer' && Number(x.balance) ? fmtMoney(x.balance) : ''}</td>
                <td className="px-4 py-3">
                  <Badge variant={SUPPLIER_STATUSES[x.status].variant}>{SUPPLIER_STATUSES[x.status].label}</Badge>
                  {x.has_gaps && x.status === 'brouillon' && (
                    <Badge variant="destructive" className="ml-1">
                      Écarts
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <FileWarning className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucune facture fournisseur</p>
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['facture', 'factures']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <NewSupplierInvoiceDialog onClose={() => setCreating(false)} onCreated={(id) => navigate(`/facturation/fournisseurs/${id}`)} />}
    </>
  )
}

function NewSupplierInvoiceDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [supplier, setSupplier] = useState<{ id: number; name: string } | null>(null)
  const [f, setF] = useState({ supplier_number: '', invoice_date: today(), total_ht: '', total_vat: '', total_ttc: '' })
  const [receptions, setReceptions] = useState<Set<number>>(new Set())
  const todo = useQuery({
    queryKey: ['receptions-to-bill', company?.id, supplier?.id],
    queryFn: () => api<{ id: number; number: string; received_on: string; delivery_note: string | null; order_number: string; total_ht: string; line_count: number }[]>(`/billing/suppliers/${supplier!.id}/to-invoice`),
    enabled: !!supplier,
  })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const amountsOk = ['total_ht', 'total_vat', 'total_ttc'].every((k) => AMOUNT.test(f[k as keyof typeof f].trim()))
  const create = useMutation({
    mutationFn: () =>
      api<SupplierInvoice>('/billing/supplier-invoices', {
        method: 'POST',
        body: { partner_id: supplier!.id, supplier_number: f.supplier_number.trim(), invoice_date: f.invoice_date, total_ht: toDec(f.total_ht), total_vat: toDec(f.total_vat), total_ttc: toDec(f.total_ttc), reception_ids: [...receptions] },
      }),
    onSuccess: (inv) => {
      void queryClient.invalidateQueries({ queryKey: ['supplier-invoices'] })
      onCreated(inv.id)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Saisir une facture fournisseur</DialogTitle>
          <DialogDescription>Recopiez l'en-tête de la facture reçue et cochez les réceptions qu'elle concerne : les lignes sont reprises et contrôlées (quantités reçues, prix commandés).</DialogDescription>
        </DialogHeader>
        {!supplier ? (
          <PartnerPicker role="supplier" value={supplier} onPick={setSupplier} />
        ) : (
          <div className="space-y-4">
            <p className="text-sm">
              Fournisseur : <b>{supplier.name}</b>{' '}
              <Button variant="ghost" size="sm" onClick={() => setSupplier(null)}>
                Changer
              </Button>
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field id="si_number" label="N° de la facture">
                <Input id="si_number" value={f.supplier_number} onChange={set('supplier_number')} />
              </Field>
              <Field id="si_date" label="Date de la facture">
                <Input id="si_date" type="date" value={f.invoice_date} onChange={set('invoice_date')} />
              </Field>
              <div />
              <Field id="si_ht" label="Total HT">
                <Input id="si_ht" inputMode="decimal" value={f.total_ht} onChange={set('total_ht')} />
              </Field>
              <Field id="si_vat" label="TVA">
                <Input id="si_vat" inputMode="decimal" value={f.total_vat} onChange={set('total_vat')} />
              </Field>
              <Field id="si_ttc" label="Total TTC">
                <Input id="si_ttc" inputMode="decimal" value={f.total_ttc} onChange={set('total_ttc')} />
              </Field>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Réceptions non encore facturées</p>
              <ul className="max-h-56 divide-y overflow-auto rounded-lg border">
                {todo.data?.map((r) => (
                  <li key={r.id}>
                    <label className="flex items-center gap-3 px-3 py-2 text-sm">
                      <input
                        type="checkbox"
                        aria-label={`Réception ${r.number}`}
                        checked={receptions.has(r.id)}
                        onChange={(e) => {
                          const next = new Set(receptions)
                          if (e.target.checked) next.add(r.id)
                          else next.delete(r.id)
                          setReceptions(next)
                        }}
                      />
                      <span className="font-mono text-xs">{r.number}</span>
                      <span className="text-muted-foreground">{fmtDate(r.received_on)}</span>
                      <span className="font-mono text-xs text-muted-foreground">{r.order_number}</span>
                      {r.delivery_note && <span className="text-xs text-muted-foreground">BL {r.delivery_note}</span>}
                      <span className="ml-auto tabular-nums">{fmtMoney(r.total_ht)} HT</span>
                    </label>
                  </li>
                ))}
                {todo.data?.length === 0 && <li className="px-3 py-3 text-center text-sm text-muted-foreground">Aucune réception à facturer (frais seuls : ajoutez des lignes ensuite).</li>}
              </ul>
            </div>
          </div>
        )}
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!supplier || !f.supplier_number.trim() || !amountsOk || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <LoaderCircle className="animate-spin" />}
            Créer et contrôler
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

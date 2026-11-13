import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, Ban, Banknote, CheckCircle2, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { SupplierPayDialog } from '@/pages/billing/dialogs'
import { PAYMENT_METHODS, SUPPLIER_STATUSES, toDec, type PaymentMethod, type SupplierInvoice, type SupplierLine } from '@/pages/billing/types'
import { fmtCost, fmtMoney, fmtQty } from '@/pages/inventory/types'
import { InfoCard } from '@/pages/sales/parts'
import { fmtDate, fmtPct } from '@/pages/sales/types'

const NUM = /^\d{1,11}([.,]\d{1,4})?$/
const show = (v: string) => String(Number(v)).replace('.', ',')

export function SupplierInvoicePage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const queryClient = useQueryClient()
  const canEdit = can(me?.permissions, 'billing:suppliers')
  const [dialog, setDialog] = useState<'approve' | 'pay' | 'line' | null>(null)
  const [edits, setEdits] = useState<Record<number, { quantity: string; unit_price: string }>>({})
  const key = ['supplier-invoice', company?.id, Number(id)]
  const invoice = useQuery({ queryKey: key, queryFn: () => api<SupplierInvoice>(`/billing/supplier-invoices/${id}`) })
  const done = (i: SupplierInvoice) => {
    queryClient.setQueryData(key, i)
    void queryClient.invalidateQueries({ queryKey: ['supplier-invoices'] })
  }
  const saveLine = useMutation({
    mutationFn: (l: SupplierLine) => {
      const e = edits[l.id]
      return api<SupplierInvoice>(`/billing/supplier-invoices/${id}/lines/${l.id}`, { method: 'PUT', body: { quantity: toDec(e.quantity), unit_price: toDec(e.unit_price), vat_rate: l.vat_rate } })
    },
    onSuccess: (i, l) => {
      const rest = { ...edits }
      delete rest[l.id]
      setEdits(rest)
      done(i)
    },
  })
  const removeLine = useMutation({ mutationFn: (lineId: number) => api<SupplierInvoice>(`/billing/supplier-invoices/${id}/lines/${lineId}`, { method: 'DELETE' }), onSuccess: done })
  const cancel = useMutation({ mutationFn: () => api<SupplierInvoice>(`/billing/supplier-invoices/${id}/cancel`, { method: 'POST' }), onSuccess: done })
  const inv = invoice.data
  if (!inv) return invoice.isPending ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <ErrorAlert error={invoice.error} />
  const draft = inv.status === 'brouillon' && canEdit
  const st = SUPPLIER_STATUSES[inv.status]
  return (
    <>
      <Link to="/facturation?vue=fournisseurs" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Factures fournisseur
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold">
            Facture <span className="font-mono">{inv.supplier_number}</span>
            <Badge variant={st.variant}>{st.label}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/fournisseurs/${inv.partner_id}`} className="hover:underline">
              {inv.partner_name}
            </Link>{' '}
            · du {fmtDate(inv.invoice_date)} · n° interne <span className="font-mono">{inv.number}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canEdit && inv.status !== 'annulee' && Number(inv.paid_amount) === 0 && (
            <Button variant="ghost" disabled={cancel.isPending} onClick={() => window.confirm('Annuler cette facture (doublon, erreur) ?') && cancel.mutate()}>
              <Ban /> Annuler
            </Button>
          )}
          {draft && (
            <Button disabled={!inv.lines.length || Object.keys(edits).length > 0} onClick={() => setDialog('approve')}>
              <CheckCircle2 /> Bon à payer
            </Button>
          )}
          {canEdit && inv.status === 'bon_a_payer' && Number(inv.balance) > 0 && (
            <Button onClick={() => setDialog('pay')}>
              <Banknote /> Payer
            </Button>
          )}
        </div>
      </div>
      <ErrorAlert error={saveLine.error ?? removeLine.error ?? cancel.error} />
      {inv.gaps.length > 0 && inv.status === 'brouillon' && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900">
          <p className="mb-1 flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" /> Écarts avec la commande et la réception
          </p>
          <ul className="list-disc pl-5">
            {inv.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}
      {inv.approval_note && <p className="mb-4 rounded-md bg-secondary px-3 py-2 text-sm">Validée malgré écart : {inv.approval_note}</p>}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <InfoCard title="Montants saisis">
          <p>HT : {fmtMoney(inv.total_ht)}</p>
          <p>TVA : {fmtMoney(inv.total_vat)}</p>
          <p className="font-medium">TTC : {fmtMoney(inv.total_ttc)}</p>
        </InfoCard>
        <InfoCard title="Calcul des lignes">
          <p className={cn(Math.abs(Number(inv.total_ht) - Number(inv.computed_ht)) > 0.05 && 'font-medium text-destructive')}>HT : {fmtMoney(inv.computed_ht)}</p>
          <p className={cn(Math.abs(Number(inv.total_vat) - Number(inv.computed_vat)) > 0.05 && 'font-medium text-destructive')}>TVA : {fmtMoney(inv.computed_vat)}</p>
        </InfoCard>
        <InfoCard title="Paiement">
          <p>Échéance : {fmtDate(inv.due_date)}</p>
          <p>Payé : {fmtMoney(inv.paid_amount)}</p>
          <p className="font-medium">Reste : {fmtMoney(inv.balance)}</p>
        </InfoCard>
      </div>
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 font-medium">Désignation</th>
              <th className="px-3 py-2.5 text-right font-medium">Reçu</th>
              <th className="w-28 px-3 py-2.5 text-right font-medium">Facturé</th>
              <th className="px-3 py-2.5 text-right font-medium">Prix commandé</th>
              <th className="w-32 px-3 py-2.5 text-right font-medium">Prix facturé</th>
              <th className="px-3 py-2.5 text-right font-medium">TVA</th>
              <th className="px-3 py-2.5 text-right font-medium">Total HT</th>
              {draft && <th className="w-36" />}
            </tr>
          </thead>
          <tbody className="divide-y">
            {inv.lines.map((l) => {
              const e = edits[l.id]
              const qtyGap = l.qty_gap !== null && Number(l.qty_gap) !== 0
              const priceGap = l.price_gap !== null && Math.abs(Number(l.price_gap)) > 0.005
              return (
                <tr key={l.id}>
                  <td className="px-3 py-2.5">
                    {l.designation}
                    <span className="block font-mono text-xs text-muted-foreground">
                      {l.reception_number} {l.order_number && `· ${l.order_number}`}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{l.expected_quantity !== null ? fmtQty(l.expected_quantity) : '—'}</td>
                  <td className={cn('px-3 py-1.5 text-right tabular-nums', qtyGap && 'font-medium text-destructive')}>
                    {draft ? (
                      <Input aria-label={`Quantité facturée ligne ${l.line_no}`} className="h-8 text-right" value={e?.quantity ?? show(l.quantity)} onChange={(ev) => setEdits({ ...edits, [l.id]: { quantity: ev.target.value, unit_price: e?.unit_price ?? show(l.unit_price) } })} />
                    ) : (
                      fmtQty(l.quantity)
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{l.expected_price !== null ? fmtCost(l.expected_price) : '—'}</td>
                  <td className={cn('px-3 py-1.5 text-right tabular-nums', priceGap && 'font-medium text-destructive')}>
                    {draft ? (
                      <Input aria-label={`Prix facturé ligne ${l.line_no}`} className="h-8 text-right" value={e?.unit_price ?? show(l.unit_price)} onChange={(ev) => setEdits({ ...edits, [l.id]: { quantity: e?.quantity ?? show(l.quantity), unit_price: ev.target.value } })} />
                    ) : (
                      fmtCost(l.unit_price)
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{fmtPct(l.vat_rate)}</td>
                  <td className="px-3 py-2.5 text-right font-medium tabular-nums">{fmtMoney(l.line_total)}</td>
                  {draft && (
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      {e && (
                        <Button size="sm" variant="outline" disabled={!NUM.test(e.quantity.trim()) || !NUM.test(e.unit_price.trim()) || saveLine.isPending} onClick={() => saveLine.mutate(l)}>
                          OK
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label={`Supprimer la ligne ${l.line_no}`} onClick={() => removeLine.mutate(l.id)}>
                        <Trash2 />
                      </Button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
        {draft && (
          <div className="border-t p-3">
            <Button variant="outline" size="sm" onClick={() => setDialog('line')}>
              <Plus /> Ligne de frais (port, emballage…)
            </Button>
          </div>
        )}
      </div>
      {inv.payments.length > 0 && (
        <div className="mt-4 max-w-xl rounded-xl border bg-card p-4 shadow-xs">
          <h3 className="mb-2 text-sm font-semibold">Paiements</h3>
          <ul className="space-y-1 text-sm">
            {inv.payments.map((p) => (
              <li key={p.id} className="flex gap-3">
                <span>{fmtDate(p.paid_on)}</span>
                <span className="text-muted-foreground">{PAYMENT_METHODS[p.method as PaymentMethod] ?? p.method}</span>
                {p.reference && <span className="text-muted-foreground">{p.reference}</span>}
                <span className="ml-auto tabular-nums">{fmtMoney(p.amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {dialog === 'approve' && <ApproveDialog invoice={inv} onDone={done} onClose={() => setDialog(null)} />}
      {dialog === 'pay' && <SupplierPayDialog invoice={inv} onDone={done} onClose={() => setDialog(null)} />}
      {dialog === 'line' && <ExpenseLineDialog invoiceId={inv.id} onDone={done} onClose={() => setDialog(null)} />}
    </>
  )
}

function ApproveDialog({ invoice, onDone, onClose }: { invoice: SupplierInvoice; onDone: (i: SupplierInvoice) => void; onClose: () => void }) {
  const [note, setNote] = useState('')
  const gaps = invoice.gaps.length > 0
  const save = useMutation({
    mutationFn: () => api<SupplierInvoice>(`/billing/supplier-invoices/${invoice.id}/approve`, { method: 'POST', body: { version: invoice.version, note: note.trim() || null } }),
    onSuccess: (i) => {
      onDone(i)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bon à payer</DialogTitle>
          <DialogDescription>{gaps ? 'La facture présente des écarts : justifiez la validation (avoir demandé au fournisseur, hausse de prix acceptée…).' : 'Aucun écart : la facture est conforme à la commande et à la réception.'}</DialogDescription>
        </DialogHeader>
        {gaps && (
          <Field id="ap_note" label="Justification">
            <Textarea id="ap_note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        )}
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={(gaps && !note.trim()) || save.isPending} onClick={() => save.mutate()}>
            Valider
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ExpenseLineDialog({ invoiceId, onDone, onClose }: { invoiceId: number; onDone: (i: SupplierInvoice) => void; onClose: () => void }) {
  const [f, setF] = useState({ designation: 'Frais de port', quantity: '1', unit_price: '', vat_rate: '20' })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const save = useMutation({
    mutationFn: () => api<SupplierInvoice>(`/billing/supplier-invoices/${invoiceId}/lines`, { method: 'POST', body: { designation: f.designation.trim(), quantity: toDec(f.quantity), unit_price: toDec(f.unit_price), vat_rate: toDec(f.vat_rate) } }),
    onSuccess: (i) => {
      onDone(i)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ligne de frais</DialogTitle>
          <DialogDescription>Port, emballage, contribution… facturés en plus des articles.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field id="xl_designation" label="Désignation">
              <Input id="xl_designation" value={f.designation} onChange={set('designation')} />
            </Field>
          </div>
          <Field id="xl_qty" label="Quantité">
            <Input id="xl_qty" value={f.quantity} onChange={set('quantity')} />
          </Field>
          <Field id="xl_price" label="Prix unitaire HT">
            <Input id="xl_price" value={f.unit_price} onChange={set('unit_price')} />
          </Field>
          <Field id="xl_vat" label="TVA %">
            <Input id="xl_vat" value={f.vat_rate} onChange={set('vat_rate')} />
          </Field>
        </div>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!f.designation.trim() || !NUM.test(f.quantity) || !NUM.test(f.unit_price) || !NUM.test(f.vat_rate) || save.isPending} onClick={() => save.mutate()}>
            Ajouter
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { cn } from '@/lib/utils'
import { moneyOk, PAYMENT_METHODS, toDec, type CustomerAccount, type Invoice, type Payment, type PaymentMethod, type SupplierInvoice } from '@/pages/billing/types'
import { fmtMoney, fmtQty } from '@/pages/inventory/types'
import type { PartnerPage } from '@/pages/partners/types'
import { fmtDate, today } from '@/pages/sales/types'

const NUM = /^\d{1,11}([.,]\d{1,4})?$/

/** Recherche d'un tiers (client ou fournisseur). */
export function PartnerPicker({ role, value, onPick }: { role: 'customer' | 'supplier'; value: { id: number; name: string } | null; onPick: (p: { id: number; name: string }) => void }) {
  const { company } = useAuth()
  const [search, setSearch] = useState('')
  const q = useDebounced(search.trim())
  const results = useQuery({
    queryKey: ['partners', company?.id, `${role}-picker`, q],
    queryFn: () => api<PartnerPage>(`/partners?role=${role}&active=true&limit=8&q=${encodeURIComponent(q)}`),
  })
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input autoFocus aria-label={role === 'customer' ? 'Client' : 'Fournisseur'} placeholder="Rechercher…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <ul className="max-h-48 divide-y overflow-auto rounded-lg border">
        {results.data?.items.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onPick({ id: p.id, name: p.name })}
              className={cn('flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-secondary/50', value?.id === p.id && 'bg-primary/5 font-medium')}
            >
              <span>{p.name}</span>
              <span className="font-mono text-xs text-muted-foreground">{p.code}</span>
            </button>
          </li>
        ))}
        {results.data?.total === 0 && <li className="px-3 py-3 text-center text-sm text-muted-foreground">Aucun résultat</li>}
      </ul>
    </div>
  )
}

export function NewFreeInvoiceDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const queryClient = useQueryClient()
  const [customer, setCustomer] = useState<{ id: number; name: string } | null>(null)
  const create = useMutation({
    mutationFn: () => api<Invoice>('/billing/invoices', { method: 'POST', body: { customer_id: customer!.id } }),
    onSuccess: (inv) => {
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      onCreated(inv.id)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Facture libre</DialogTitle>
          <DialogDescription>Pour une prestation sans livraison (gardiennage, main-d'œuvre…). Les livraisons se facturent depuis « À facturer ».</DialogDescription>
        </DialogHeader>
        <PartnerPicker role="customer" value={customer} onPick={setCustomer} />
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!customer || create.isPending} onClick={() => create.mutate()}>
            Créer le brouillon
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Ligne libre d'une facture ou d'un avoir en brouillon. */
export function FreeLineDialog({ invoiceId, onDone, onClose }: { invoiceId: number; onDone: (i: Invoice) => void; onClose: () => void }) {
  const [f, setF] = useState({ designation: '', quantity: '1', unit_price: '', discount_pct: '0', vat_rate: '20' })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const valid = f.designation.trim() && NUM.test(f.quantity) && Number(toDec(f.quantity)) > 0 && NUM.test(f.unit_price) && NUM.test(f.discount_pct) && NUM.test(f.vat_rate)
  const save = useMutation({
    mutationFn: () =>
      api<Invoice>(`/billing/invoices/${invoiceId}/lines`, {
        method: 'POST',
        body: { designation: f.designation.trim(), quantity: toDec(f.quantity), unit_price: toDec(f.unit_price), discount_pct: toDec(f.discount_pct), vat_rate: toDec(f.vat_rate) },
      }),
    onSuccess: (i) => {
      onDone(i)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ajouter une ligne</DialogTitle>
          <DialogDescription>Prestation, frais de port, geste commercial (sur un avoir)…</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field id="fl_designation" label="Désignation">
              <Input id="fl_designation" autoFocus value={f.designation} onChange={set('designation')} />
            </Field>
          </div>
          <Field id="fl_qty" label="Quantité">
            <Input id="fl_qty" inputMode="decimal" value={f.quantity} onChange={set('quantity')} />
          </Field>
          <Field id="fl_price" label="Prix unitaire HT">
            <Input id="fl_price" inputMode="decimal" value={f.unit_price} onChange={set('unit_price')} />
          </Field>
          <Field id="fl_discount" label="Remise %">
            <Input id="fl_discount" inputMode="decimal" value={f.discount_pct} onChange={set('discount_pct')} />
          </Field>
          <Field id="fl_vat" label="TVA %">
            <Input id="fl_vat" inputMode="decimal" value={f.vat_rate} onChange={set('vat_rate')} />
          </Field>
        </div>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            Ajouter
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Avoir sur une facture émise : tout, ou certaines quantités. */
export function CreditNoteDialog({ invoice, onDone, onClose }: { invoice: Invoice; onDone: (note: Invoice) => void; onClose: () => void }) {
  const [full, setFull] = useState(true)
  const [reason, setReason] = useState('')
  const [qty, setQty] = useState<Record<number, string>>({})
  const lines = invoice.lines.filter((l) => Number(l.creditable_qty ?? 0) > 0)
  const chosen = Object.entries(qty).filter(([, v]) => v.trim() && Number(toDec(v)) > 0)
  const bad = chosen.some(([id, v]) => !NUM.test(v.trim()) || Number(toDec(v)) > Number(lines.find((l) => l.id === Number(id))?.creditable_qty ?? 0))
  const save = useMutation({
    mutationFn: () =>
      api<Invoice>(`/billing/invoices/${invoice.id}/credit-note`, {
        method: 'POST',
        body: { full, reason: reason.trim(), lines: full ? [] : chosen.map(([id, v]) => ({ line_id: Number(id), quantity: toDec(v) })) },
      }),
    onSuccess: (note) => {
      onDone(note)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Avoir sur la facture {invoice.number}</DialogTitle>
          <DialogDescription>
            Une facture émise ne se modifie pas : l'avoir l'annule en tout ou partie. Il est préparé en brouillon, vous l'émettez ensuite. Le retour de marchandise en stock se
            saisit à part (ajustement « retour client »).
          </DialogDescription>
        </DialogHeader>
        <CheckRow checked={full} onChange={setFull} title="Annuler toute la facture" description="Sinon, choisissez les quantités à reprendre ligne par ligne." />
        {!full && (
          <div className="max-h-64 overflow-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Ligne</th>
                  <th className="px-3 py-2 text-right">Reprenable</th>
                  <th className="w-28 px-3 py-2">À reprendre</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {lines.map((l) => (
                  <tr key={l.id}>
                    <td className="px-3 py-2">{l.designation}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtQty(l.creditable_qty ?? '0')}</td>
                    <td className="px-3 py-1.5">
                      <Input aria-label={`Reprendre ligne ${l.line_no}`} className="h-8 text-right" inputMode="decimal" value={qty[l.id] ?? ''} onChange={(e) => setQty({ ...qty, [l.id]: e.target.value })} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Field id="cn_reason" label="Motif (imprimé sur l'avoir)">
          <Textarea id="cn_reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!reason.trim() || (!full && (!chosen.length || bad)) || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Préparer l'avoir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Encaissement : lettrage automatique (plus anciennes d'abord) ou sur les factures choisies. */
export function PaymentDialog({
  customerId,
  invoice,
  onDone,
  onClose,
}: {
  customerId?: number
  invoice?: Invoice
  onDone: (p: Payment) => void
  onClose: () => void
}) {
  const { company } = useAuth()
  const [customer, setCustomer] = useState<{ id: number; name: string } | null>(customerId ? { id: customerId, name: '' } : null)
  const [amount, setAmount] = useState(invoice ? String(Number(invoice.balance)).replace('.', ',') : '')
  const [paidOn, setPaidOn] = useState(today())
  const [method, setMethod] = useState<PaymentMethod>('virement')
  const [reference, setReference] = useState('')
  const [mode, setMode] = useState<'auto' | 'manual'>(invoice ? 'manual' : 'auto')
  const [alloc, setAlloc] = useState<Record<number, string>>(invoice ? { [invoice.id]: String(Number(invoice.balance)).replace('.', ',') } : {})
  const account = useQuery({
    queryKey: ['customer-account', company?.id, customer?.id],
    queryFn: () => api<CustomerAccount>(`/billing/customers/${customer!.id}/account`),
    enabled: !!customer,
  })
  const allocations = Object.entries(alloc).filter(([, v]) => v.trim() && Number(toDec(v)) > 0)
  const allocated = allocations.reduce((s, [, v]) => s + Number(toDec(v)), 0)
  const over = mode === 'manual' && moneyOk(amount) && allocated > Number(toDec(amount)) + 0.001
  const save = useMutation({
    mutationFn: () =>
      api<Payment>('/billing/payments', {
        method: 'POST',
        body: {
          customer_id: customer!.id,
          paid_on: paidOn,
          amount: toDec(amount),
          method,
          reference: reference.trim() || null,
          allocations: mode === 'auto' ? null : allocations.map(([id, v]) => ({ invoice_id: Number(id), amount: toDec(v) })),
        },
      }),
    onSuccess: (p) => {
      onDone(p)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Encaisser un règlement</DialogTitle>
          <DialogDescription>Virement reçu, chèque, carte… Le montant est lettré sur les factures du client ; un surplus reste en crédit.</DialogDescription>
        </DialogHeader>
        {!customerId && <PartnerPicker role="customer" value={customer} onPick={setCustomer} />}
        <div className="grid gap-4 sm:grid-cols-4">
          <Field id="pay_amount" label="Montant">
            <Input id="pay_amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field id="pay_date" label="Reçu le">
            <Input id="pay_date" type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
          </Field>
          <Field id="pay_method" label="Mode">
            <NativeSelect id="pay_method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
              {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="pay_ref" label="Référence">
            <Input id="pay_ref" placeholder="N° de chèque…" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </div>
        {customer && (
          <div className="space-y-2">
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" checked={mode === 'auto'} onChange={() => setMode('auto')} /> Lettrage automatique (plus anciennes d'abord)
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" checked={mode === 'manual'} onChange={() => setMode('manual')} /> Choisir les factures
              </label>
            </div>
            {mode === 'manual' && (
              <div className="max-h-56 overflow-auto rounded-lg border">
                <table className="w-full text-sm">
                  <tbody className="divide-y">
                    {account.data?.invoices.map((i) => (
                      <tr key={i.id}>
                        <td className="px-3 py-2 font-mono text-xs">{i.number}</td>
                        <td className="px-3 py-2 text-muted-foreground">échéance {fmtDate(i.due_date)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">reste {fmtMoney(i.balance)}</td>
                        <td className="w-28 px-3 py-1.5">
                          <Input aria-label={`Affecter à ${i.number}`} className="h-8 text-right" inputMode="decimal" value={alloc[i.id] ?? ''} onChange={(e) => setAlloc({ ...alloc, [i.id]: e.target.value })} />
                        </td>
                      </tr>
                    ))}
                    {account.data?.invoices.length === 0 && (
                      <tr>
                        <td className="px-3 py-3 text-center text-muted-foreground">Aucune facture à payer : le règlement restera en crédit.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
            {account.data && (
              <p className="text-xs text-muted-foreground">
                Dû par le client : {fmtMoney(account.data.total_due)}
                {Number(account.data.overdue) > 0 && <span className="text-destructive"> dont {fmtMoney(account.data.overdue)} en retard</span>}
              </p>
            )}
          </div>
        )}
        {over && <p className="text-sm text-destructive">Les affectations dépassent le montant du règlement.</p>}
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!customer || !moneyOk(amount) || over || !paidOn || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer le règlement
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Impute le crédit d'un avoir sur une facture du même client. */
export function ApplyCreditDialog({ note, onDone, onClose }: { note: Invoice; onDone: () => void; onClose: () => void }) {
  const { company } = useAuth()
  const account = useQuery({ queryKey: ['customer-account', company?.id, note.customer_id], queryFn: () => api<CustomerAccount>(`/billing/customers/${note.customer_id}/account`) })
  const [target, setTarget] = useState('')
  const invoice = account.data?.invoices.find((i) => String(i.id) === target)
  const max = invoice ? Math.min(Number(invoice.balance), Number(note.balance)) : 0
  const [amount, setAmount] = useState('')
  const value = amount || (max ? String(max).replace('.', ',') : '')
  const save = useMutation({
    mutationFn: () => api(`/billing/credit-notes/${note.id}/apply`, { method: 'POST', body: { invoice_id: Number(target), amount: toDec(value) } }),
    onSuccess: () => {
      onDone()
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Imputer l'avoir {note.number}</DialogTitle>
          <DialogDescription>Crédit disponible : {fmtMoney(note.balance)}. Il vient en déduction d'une autre facture du client.</DialogDescription>
        </DialogHeader>
        <Field id="ac_invoice" label="Facture">
          <NativeSelect id="ac_invoice" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">— Choisir —</option>
            {account.data?.invoices.map((i) => (
              <option key={i.id} value={i.id}>
                {i.number} · reste {fmtMoney(i.balance)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field id="ac_amount" label="Montant">
          <Input id="ac_amount" inputMode="decimal" value={value} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!target || !moneyOk(value) || save.isPending} onClick={() => save.mutate()}>
            Imputer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Paiement d'une facture fournisseur « bon à payer ». */
export function SupplierPayDialog({ invoice, onDone, onClose }: { invoice: SupplierInvoice; onDone: (i: SupplierInvoice) => void; onClose: () => void }) {
  const [amount, setAmount] = useState(String(Number(invoice.balance)).replace('.', ','))
  const [paidOn, setPaidOn] = useState(today())
  const [method, setMethod] = useState<PaymentMethod>('virement')
  const [reference, setReference] = useState('')
  const save = useMutation({
    mutationFn: () => api<SupplierInvoice>(`/billing/supplier-invoices/${invoice.id}/payments`, { method: 'POST', body: { amount: toDec(amount), paid_on: paidOn, method, reference: reference.trim() || null } }),
    onSuccess: (i) => {
      onDone(i)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Payer la facture {invoice.supplier_number}</DialogTitle>
          <DialogDescription>
            {invoice.partner_name} · reste à payer {fmtMoney(invoice.balance)}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="sp_amount" label="Montant">
            <Input id="sp_amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field id="sp_date" label="Payé le">
            <Input id="sp_date" type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
          </Field>
          <Field id="sp_method" label="Mode">
            <NativeSelect id="sp_method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
              {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="sp_ref" label="Référence">
            <Input id="sp_ref" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </div>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!moneyOk(amount) || save.isPending} onClick={() => save.mutate()}>
            Enregistrer le paiement
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

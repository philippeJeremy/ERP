import { useMutation } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { orderTitle, qty, type Order } from '@/pages/purchasing/types'

const today = () => new Date().toISOString().slice(0, 10)
const qtyOk = (v: string) => /^\d{1,11}([.,]\d{1,3})?$/.test(v.trim())

/** Motif obligatoire : refus, annulation, clôture. */
export function ReasonDialog({
  title,
  description,
  label,
  confirm,
  destructive,
  path,
  onDone,
  onClose,
}: {
  title: string
  description: string
  label: string
  confirm: string
  destructive?: boolean
  path: string
  onDone: (o: Order) => void
  onClose: () => void
}) {
  const [reason, setReason] = useState('')
  const send = useMutation({
    mutationFn: () => api<Order>(path, { method: 'POST', body: { reason: reason.trim() } }),
    onSuccess: (o) => {
      onDone(o)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Field id="reason" label={label}>
          <Textarea id="reason" rows={3} autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Retour
          </Button>
          <Button variant={destructive ? 'destructive' : 'default'} disabled={!reason.trim() || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            {confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Accusé de commande : ce que le fournisseur s'engage à livrer, et quand. */
export function AckDialog({ order, onDone, onClose }: { order: Order; onDone: (o: Order) => void; onClose: () => void }) {
  const [reference, setReference] = useState(order.supplier_reference ?? '')
  const [rows, setRows] = useState(
    order.lines.map((l) => ({ id: l.id, qty: String(Number(l.confirmed_qty ?? l.quantity)).replace('.', ','), date: l.confirmed_date ?? order.expected_date ?? '' })),
  )
  const valid = rows.every((r) => qtyOk(r.qty))
  const send = useMutation({
    mutationFn: () =>
      api<Order>(`/purchasing/orders/${order.id}/acknowledge`, {
        method: 'POST',
        body: { supplier_reference: reference.trim() || null, lines: rows.map((r) => ({ line_id: r.id, confirmed_qty: r.qty.replace(',', '.'), confirmed_date: r.date || null })) },
      }),
    onSuccess: (o) => {
      onDone(o)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Accusé de commande — {orderTitle(order)}</DialogTitle>
          <DialogDescription>Recopiez la réponse du fournisseur : les quantités qu'il confirme et ses dates de livraison. Une quantité inférieure signale une rupture.</DialogDescription>
        </DialogHeader>
        <div className="w-60">
          <Field id="ack_ref" label="N° d'accusé du fournisseur">
            <Input id="ack_ref" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </div>
        <div className="max-h-96 overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Article</th>
                <th className="px-3 py-2 text-right">Commandé</th>
                <th className="w-28 px-3 py-2">Confirmé</th>
                <th className="w-40 px-3 py-2">Livraison prévue</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {order.lines.map((l, i) => (
                <tr key={l.id}>
                  <td className="px-3 py-2">{l.designation}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{qty(l.quantity)}</td>
                  <td className="px-3 py-1.5">
                    <Input aria-label={`Quantité confirmée ligne ${l.line_no}`} className="h-8 text-right" value={rows[i].qty} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, qty: e.target.value } : r)))} />
                  </td>
                  <td className="px-3 py-1.5">
                    <Input type="date" aria-label={`Date prévue ligne ${l.line_no}`} className="h-8" value={rows[i].date} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, date: e.target.value } : r)))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!valid || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer l'accusé
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Réception d'une livraison : quantités reçues par ligne, n° du bon de livraison. */
export function ReceiveDialog({ order, onDone, onClose }: { order: Order; onDone: (o: Order) => void; onClose: () => void }) {
  const open = order.lines.filter((l) => Number(l.received_qty) < Number(l.quantity))
  const [date, setDate] = useState(today())
  const [note, setNote] = useState('')
  const [deliveryNote, setDeliveryNote] = useState('')
  // Par défaut : tout le reste à recevoir (on corrige ce qui manque).
  const [rows, setRows] = useState(open.map((l) => ({ id: l.id, qty: String(Number(l.quantity) - Number(l.received_qty)).replace('.', ',') })))
  const invalid = rows.some((r, i) => !qtyOk(r.qty) || Number(r.qty.replace(',', '.')) > Number(open[i].quantity) - Number(open[i].received_qty))
  const nothing = rows.every((r) => Number(r.qty.replace(',', '.')) === 0)
  const send = useMutation({
    mutationFn: () =>
      api<Order>(`/purchasing/orders/${order.id}/receive`, {
        method: 'POST',
        body: { received_on: date, delivery_note: deliveryNote.trim() || null, note: note.trim() || null, lines: rows.map((r) => ({ line_id: r.id, quantity: r.qty.replace(',', '.') })) },
      }),
    onSuccess: (o) => {
      onDone(o)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Réception — {orderTitle(order)}</DialogTitle>
          <DialogDescription>Comptez ce qui est arrivé. Ce qui manque reste en reliquat : une nouvelle réception le soldera.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field id="rcv_date" label="Reçu le">
            <Input id="rcv_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field id="rcv_bl" label="N° du bon de livraison">
            <Input id="rcv_bl" value={deliveryNote} onChange={(e) => setDeliveryNote(e.target.value)} />
          </Field>
        </div>
        <div className="max-h-96 overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Article</th>
                <th className="px-3 py-2 text-right">Commandé</th>
                <th className="px-3 py-2 text-right">Déjà reçu</th>
                <th className="w-28 px-3 py-2">Reçu ce jour</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {open.map((l, i) => (
                <tr key={l.id}>
                  <td className="px-3 py-2">
                    {l.designation}
                    {l.supplier_ref && <span className="block font-mono text-xs text-muted-foreground">{l.supplier_ref}</span>}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{qty(l.quantity)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{qty(l.received_qty)}</td>
                  <td className="px-3 py-1.5">
                    <Input aria-label={`Reçu ligne ${l.line_no}`} className="h-8 text-right" value={rows[i].qty} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, qty: e.target.value } : r)))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Field id="rcv_note" label="Remarque (colis abîmé, erreur de référence…)">
          <Textarea id="rcv_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {invalid && <p className="text-sm text-destructive">Une quantité dépasse le reste à recevoir (ou est mal écrite).</p>}
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={invalid || nothing || !date || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer la réception
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

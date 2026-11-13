import { useMutation } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { useLocations } from '@/pages/inventory/hooks'
import { DOT_RE, fmtQty } from '@/pages/inventory/types'
import { today, type Order } from '@/pages/sales/types'

/** Action avec motif obligatoire (refus, annulation, clôture). */
export function ReasonDialog<T>({
  title,
  description,
  confirm,
  path,
  onDone,
  onClose,
}: {
  title: string
  description: string
  confirm: string
  path: string
  onDone: (result: T) => void
  onClose: () => void
}) {
  const [reason, setReason] = useState('')
  const send = useMutation({
    mutationFn: () => api<T>(path, { method: 'POST', body: { reason: reason.trim() } }),
    onSuccess: (result) => {
      onDone(result)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Field id="reason" label="Motif">
          <Textarea id="reason" rows={3} autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Retour
          </Button>
          <Button variant="destructive" disabled={!reason.trim() || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            {confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Dépassement d'encours : on confirme en connaissance de cause (force). */
export function CreditDialog({ message, pending, onForce, onClose }: { message: string; pending: boolean; onForce: () => void; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Encours dépassé</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Ne pas confirmer
          </Button>
          <Button variant="destructive" disabled={pending} onClick={onForce}>
            {pending && <LoaderCircle className="animate-spin" />}
            Confirmer quand même
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const QTY_RE = /^\d{1,11}([.,]\d{1,3})?$/

/** Livraison : quantités à livrer par ligne (le reste par défaut, limité au stock). Le stock
 * sort automatiquement des DOT les plus anciens, sauf DOT ou emplacement choisi. */
export function DeliverDialog({ order, onDone, onClose }: { order: Order; onDone: (o: Order) => void; onClose: () => void }) {
  const open = order.lines.filter((l) => Number(l.remaining_qty) > 0)
  const locations = useLocations(order.site.id)
  const [date, setDate] = useState(today())
  const [carrier, setCarrier] = useState('')
  const [note, setNote] = useState('')
  const [rows, setRows] = useState(
    open.map((l) => {
      const max = l.on_hand === null ? Number(l.remaining_qty) : Math.min(Number(l.remaining_qty), Math.max(0, Number(l.on_hand)))
      return { lineId: l.id, qty: String(max).replace('.', ','), dot: l.dot, location: '' }
    }),
  )
  const patch = (i: number, change: Partial<(typeof rows)[number]>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)))
  const lines = new Map(open.map((l) => [l.id, l]))
  const num = (v: string) => Number(v.replace(',', '.'))
  const bad = rows.some((r) => !QTY_RE.test(r.qty.trim()) || num(r.qty) > Number(lines.get(r.lineId)!.remaining_qty) || !DOT_RE.test(r.dot.trim()))
  const toSend = rows.filter((r) => num(r.qty) > 0)
  const send = useMutation({
    mutationFn: () =>
      api<Order>(`/sales/orders/${order.id}/deliver`, {
        method: 'POST',
        body: {
          delivered_on: date,
          carrier: carrier.trim() || null,
          note: note.trim() || null,
          lines: toSend.map((r) => ({ line_id: r.lineId, quantity: r.qty.replace(',', '.'), dot: r.dot.trim() || null, location_id: r.location ? Number(r.location) : null })),
        },
      }),
    onSuccess: (o) => {
      onDone(o)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Livrer — {order.number}</DialogTitle>
          <DialogDescription>
            Le stock sort du dépôt {order.site.name}, les DOT les plus anciens d'abord (sauf DOT choisi). Ce qui n'est pas livré reste en reliquat.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field id="dlv_date" label="Livré le">
            <Input id="dlv_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field id="dlv_carrier" label="Transport">
            <Input id="dlv_carrier" placeholder="Retrait comptoir, transporteur…" value={carrier} onChange={(e) => setCarrier(e.target.value)} />
          </Field>
        </div>
        <div className="max-h-80 overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Article</th>
                <th className="px-3 py-2 text-right">Reste</th>
                <th className="px-3 py-2 text-right">Stock</th>
                <th className="w-24 px-3 py-2">À livrer</th>
                <th className="w-24 px-3 py-2">DOT</th>
                <th className="w-32 px-3 py-2">Emplacement</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r, i) => {
                const l = lines.get(r.lineId)!
                return (
                  <tr key={r.lineId}>
                    <td className="px-3 py-2">
                      {l.designation}
                      {!l.article && <span className="block text-xs text-muted-foreground">Ligne libre</span>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtQty(l.remaining_qty)}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground tabular-nums">{l.on_hand !== null ? fmtQty(l.on_hand) : ''}</td>
                    <td className="px-3 py-1.5">
                      <Input aria-label={`À livrer ligne ${l.line_no}`} className="h-8 text-right" value={r.qty} onChange={(e) => patch(i, { qty: e.target.value })} />
                    </td>
                    <td className="px-3 py-1.5">
                      {l.article && (
                        <Input aria-label={`DOT ligne ${l.line_no}`} className="h-8 font-mono" placeholder="FIFO" maxLength={4} value={r.dot} onChange={(e) => patch(i, { dot: e.target.value })} />
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      {l.article && (
                        <NativeSelect aria-label={`Emplacement ligne ${l.line_no}`} className="h-8" value={r.location} onChange={(e) => patch(i, { location: e.target.value })}>
                          <option value="">Tout le dépôt</option>
                          {locations.data?.map((loc) => (
                            <option key={loc.id} value={loc.id}>
                              {loc.code}
                            </option>
                          ))}
                        </NativeSelect>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <Field id="dlv_note" label="Remarque (imprimée sur le bon de livraison)">
          <Textarea id="dlv_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {bad && <p className="text-sm text-destructive">Une quantité ou un DOT est invalide, ou dépasse le reste à livrer.</p>}
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={bad || toSend.length === 0 || !date || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            Valider la livraison
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

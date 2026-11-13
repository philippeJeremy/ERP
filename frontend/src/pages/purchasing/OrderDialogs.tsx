import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { useAuth } from '@/auth/useAuth'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { DOT_RE, type Location } from '@/pages/inventory/types'
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
interface ReceiveRow {
  key: number
  lineId: number
  qty: string
  dot: string
  locationId: string
}

export function ReceiveDialog({ order, onDone, onClose }: { order: Order; onDone: (o: Order) => void; onClose: () => void }) {
  const { me, company } = useAuth()
  const open = order.lines.filter((l) => Number(l.received_qty) < Number(l.quantity))
  const [date, setDate] = useState(today())
  const [note, setNote] = useState('')
  const [deliveryNote, setDeliveryNote] = useState('')
  // Par défaut : tout le reste à recevoir (on corrige ce qui manque). Une ligne peut être
  // répartie sur plusieurs DOT ou emplacements (« + DOT »).
  const [rows, setRows] = useState<ReceiveRow[]>(
    open.map((l, i) => ({ key: i, lineId: l.id, qty: String(Number(l.quantity) - Number(l.received_qty)).replace('.', ','), dot: '', locationId: '' })),
  )
  const [nextKey, setNextKey] = useState(open.length)
  const seeStock = can(me?.permissions, 'inventory:read')
  const locations = useQuery({
    queryKey: ['locations', company?.id, order.site.id, 'active'],
    queryFn: () => api<Location[]>(`/inventory/sites/${order.site.id}/locations?active=true`),
    enabled: seeStock,
  })
  const num = (v: string) => Number(v.replace(',', '.'))
  const byLine = new Map<number, number>()
  for (const r of rows) byLine.set(r.lineId, (byLine.get(r.lineId) ?? 0) + (qtyOk(r.qty) ? num(r.qty) : 0))
  const over = open.filter((l) => (byLine.get(l.id) ?? 0) > Number(l.quantity) - Number(l.received_qty))
  const badQty = rows.some((r) => !qtyOk(r.qty))
  const badDot = rows.some((r) => !DOT_RE.test(r.dot.trim()))
  const nothing = rows.every((r) => num(r.qty) === 0)
  const patch = (key: number, change: Partial<ReceiveRow>) => setRows(rows.map((r) => (r.key === key ? { ...r, ...change } : r)))
  const split = (row: ReceiveRow) => {
    const index = rows.findIndex((r) => r.key === row.key)
    setRows([...rows.slice(0, index + 1), { key: nextKey, lineId: row.lineId, qty: '0', dot: '', locationId: row.locationId }, ...rows.slice(index + 1)])
    setNextKey(nextKey + 1)
  }
  const send = useMutation({
    mutationFn: () =>
      api<Order>(`/purchasing/orders/${order.id}/receive`, {
        method: 'POST',
        body: {
          received_on: date,
          delivery_note: deliveryNote.trim() || null,
          note: note.trim() || null,
          lines: rows.map((r) => ({ line_id: r.lineId, quantity: r.qty.replace(',', '.'), dot: r.dot.trim(), location_id: r.locationId ? Number(r.locationId) : null })),
        },
      }),
    onSuccess: (o) => {
      onDone(o)
      onClose()
    },
  })
  const lines = new Map(open.map((l) => [l.id, l]))
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Réception — {orderTitle(order)}</DialogTitle>
          <DialogDescription>
            Comptez ce qui est arrivé : les articles entrent en stock au dépôt {order.site.name}. Ce qui manque reste en reliquat. Pour des pneus de DOT
            différents, répartissez la ligne avec « + DOT ».
          </DialogDescription>
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
                <th className="px-3 py-2 text-right">Reste</th>
                <th className="w-24 px-3 py-2">Reçu</th>
                <th className="w-24 px-3 py-2" title="Semaine + année de fabrication, ex. 2324">
                  DOT
                </th>
                {seeStock && <th className="w-36 px-3 py-2">Emplacement</th>}
                <th className="w-16" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => {
                const l = lines.get(r.lineId)!
                const first = rows.find((x) => x.lineId === r.lineId) === r
                const stocked = l.article_id !== null
                return (
                  <tr key={r.key} className={cn(!first && 'bg-secondary/20')}>
                    <td className="px-3 py-2">
                      {first ? (
                        <>
                          {l.designation}
                          {l.supplier_ref && <span className="block font-mono text-xs text-muted-foreground">{l.supplier_ref}</span>}
                          {!stocked && <span className="block text-xs text-muted-foreground">Ligne libre : n'entre pas en stock</span>}
                        </>
                      ) : (
                        <span className="pl-4 text-xs text-muted-foreground">↳ autre DOT / emplacement</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{first ? qty(String(Number(l.quantity) - Number(l.received_qty))) : ''}</td>
                    <td className="px-3 py-1.5">
                      <Input aria-label={`Reçu ligne ${l.line_no}${first ? '' : ' (suite)'}`} className="h-8 text-right" value={r.qty} onChange={(e) => patch(r.key, { qty: e.target.value })} />
                    </td>
                    <td className="px-3 py-1.5">
                      {stocked && (
                        <Input
                          aria-label={`DOT ligne ${l.line_no}${first ? '' : ' (suite)'}`}
                          className={cn('h-8 font-mono', !DOT_RE.test(r.dot.trim()) && 'border-destructive')}
                          inputMode="numeric"
                          maxLength={4}
                          placeholder="—"
                          value={r.dot}
                          onChange={(e) => patch(r.key, { dot: e.target.value })}
                        />
                      )}
                    </td>
                    {seeStock && (
                      <td className="px-3 py-1.5">
                        {stocked && (
                          <NativeSelect aria-label={`Emplacement ligne ${l.line_no}`} className="h-8" value={r.locationId} onChange={(e) => patch(r.key, { locationId: e.target.value })}>
                            {locations.data?.map((loc) => (
                              <option key={loc.id} value={loc.is_default ? '' : loc.id}>
                                {loc.code}
                              </option>
                            ))}
                          </NativeSelect>
                        )}
                      </td>
                    )}
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      {stocked && first && (
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => split(r)}>
                          + DOT
                        </Button>
                      )}
                      {!first && (
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" aria-label="Retirer" onClick={() => setRows(rows.filter((x) => x.key !== r.key))}>
                          ✕
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <Field id="rcv_note" label="Remarque (colis abîmé, erreur de référence…)">
          <Textarea id="rcv_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {badQty && <p className="text-sm text-destructive">Une quantité est mal écrite.</p>}
        {over.length > 0 && <p className="text-sm text-destructive">Ligne {over.map((l) => l.line_no).join(', ')} : plus que le reste à recevoir.</p>}
        {badDot && <p className="text-sm text-destructive">DOT : 4 chiffres, la semaine (01 à 53) puis l'année. Ex. 2324.</p>}
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={badQty || badDot || over.length > 0 || nothing || !date || send.isPending} onClick={() => send.mutate()}>
            {send.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer la réception
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

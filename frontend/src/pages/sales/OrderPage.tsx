import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, CheckCircle2, FileDown, LoaderCircle, PackageCheck, RotateCcw, Trash2, Truck } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api, ApiError, openFile } from '@/lib/api'
import { can } from '@/lib/permissions'
import { STOCK_KEYS } from '@/pages/inventory/hooks'
import { fmtMoney, fmtQty } from '@/pages/inventory/types'
import { CreditDialog, DeliverDialog, ReasonDialog } from '@/pages/sales/dialogs'
import { LineDialog, type LineBody } from '@/pages/sales/LineDialog'
import { DocTotals, InfoCard, SalesLinesTable } from '@/pages/sales/parts'
import { fmtDate, ORDER_STATUSES, type Order, type OrderLine, type SalesLine } from '@/pages/sales/types'

export function OrderPage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'sales:manage')
  const canDeliver = can(me?.permissions, 'sales:deliver')
  const [editing, setEditing] = useState<SalesLine | 'new' | null>(null)
  const [dialog, setDialog] = useState<'deliver' | 'close' | 'cancel' | null>(null)
  const [credit, setCredit] = useState<string | null>(null)
  const key = ['order', company?.id, Number(id)]
  const order = useQuery({ queryKey: key, queryFn: () => api<Order>(`/sales/orders/${id}`) })
  const done = (o: Order) => {
    queryClient.setQueryData(key, o)
    void queryClient.invalidateQueries({ queryKey: ['orders'] })
    for (const k of STOCK_KEYS) void queryClient.invalidateQueries({ queryKey: k })
  }
  const confirm = useMutation({
    mutationFn: (force: boolean) => api<Order>(`/sales/orders/${id}/confirm`, { method: 'POST', body: { version: order.data!.version, force } }),
    onSuccess: (o) => {
      setCredit(null)
      done(o)
    },
    onError: (e) => e instanceof ApiError && e.code === 'encours_depasse' && setCredit(e.message),
  })
  const reopen = useMutation({ mutationFn: () => api<Order>(`/sales/orders/${id}/reopen`, { method: 'POST' }), onSuccess: done })
  const remove = useMutation({
    mutationFn: () => api<void>(`/sales/orders/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      navigate('/ventes?vue=commandes', { replace: true })
    },
  })
  const removeLine = useMutation({
    mutationFn: (l: SalesLine) => api<Order>(`/sales/orders/${id}/lines/${l.id}`, { method: 'DELETE' }),
    onSuccess: done,
  })
  const pdf = useMutation({ mutationFn: (deliveryId: number) => openFile(`/sales/deliveries/${deliveryId}/pdf`) })
  const o = order.data
  if (!o) return order.isPending ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <ErrorAlert error={order.error} />
  const status = ORDER_STATUSES[o.status]
  const draft = o.status === 'brouillon'
  const deliverable = o.status === 'confirmee' || o.status === 'partielle'
  const nothingDelivered = o.lines.every((l) => Number(l.delivered_qty) === 0)
  const shortage = o.lines.some((l) => l.on_hand !== null && Number(l.remaining_qty) > Number(l.on_hand))
  const overCredit = o.credit.limit !== null && Number(o.credit.outstanding) > Number(o.credit.limit)
  const saveLine = (body: LineBody) =>
    api<Order>(editing === 'new' ? `/sales/orders/${id}/lines` : `/sales/orders/${id}/lines/${(editing as SalesLine).id}`, {
      method: editing === 'new' ? 'POST' : 'PUT',
      body,
    }).then(done)
  return (
    <>
      <Link to="/ventes?vue=commandes" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Commandes client
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold">
            Commande <span className="font-mono">{o.number}</span>
            <Badge variant={status.variant}>{status.label}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/clients/${o.customer.id}`} className="hover:underline">
              {o.customer.name}
            </Link>{' '}
            · du {fmtDate(o.order_date)}
            {o.quote && (
              <>
                {' '}
                · devis{' '}
                <Link to={`/ventes/devis/${o.quote.id}`} className="font-mono hover:underline">
                  {o.quote.number}
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage && draft && (
            <>
              {!o.quote && (
                <Button variant="ghost" disabled={remove.isPending} onClick={() => window.confirm('Supprimer ce brouillon ?') && remove.mutate()}>
                  <Trash2 /> Supprimer
                </Button>
              )}
              <Button variant="outline" onClick={() => setDialog('cancel')}>
                <Ban /> Annuler
              </Button>
              <Button disabled={!o.lines.length || confirm.isPending} onClick={() => confirm.mutate(false)}>
                {confirm.isPending ? <LoaderCircle className="animate-spin" /> : <CheckCircle2 />}
                Confirmer (réserver le stock)
              </Button>
            </>
          )}
          {canManage && o.status === 'confirmee' && nothingDelivered && (
            <>
              <Button variant="outline" disabled={reopen.isPending} onClick={() => reopen.mutate()}>
                <RotateCcw /> Modifier
              </Button>
              <Button variant="outline" onClick={() => setDialog('cancel')}>
                <Ban /> Annuler
              </Button>
            </>
          )}
          {canManage && o.status === 'partielle' && (
            <Button variant="outline" onClick={() => setDialog('close')}>
              <PackageCheck /> Solder le reliquat
            </Button>
          )}
          {canDeliver && deliverable && (
            <Button onClick={() => setDialog('deliver')}>
              <Truck /> Livrer
            </Button>
          )}
        </div>
      </div>
      <ErrorAlert error={(confirm.error instanceof ApiError && confirm.error.code === 'encours_depasse' ? null : confirm.error) ?? reopen.error ?? remove.error ?? removeLine.error ?? pdf.error} />
      {deliverable && shortage && (
        <p className="mb-4 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">Rupture : le stock du dépôt ne couvre pas tout le reste à livrer. Livrez ce qui est disponible ou commandez au fournisseur.</p>
      )}
      {o.cancel_reason && <p className="mb-4 rounded-md bg-secondary px-3 py-2 text-sm">Motif : {o.cancel_reason}</p>}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <InfoCard title="Livraison">
          {(o.delivery_address ?? [o.customer.name, ...o.customer.delivery_address].join('\n')).split('\n').map((x, i) => (
            <p key={i} className={i === 0 ? 'font-medium' : 'text-muted-foreground'}>
              {x}
            </p>
          ))}
          <p className="text-xs">Depuis : {o.site.name}</p>
        </InfoCard>
        <InfoCard title="Conditions">
          <p>Règlement : {o.customer.payment_terms ?? '—'}</p>
          {o.requested_date && <p>Livraison souhaitée : {fmtDate(o.requested_date)}</p>}
          {o.customer_reference && <p>Réf. client : {o.customer_reference}</p>}
        </InfoCard>
        <InfoCard title="Encours du client">
          <p className={overCredit ? 'font-medium text-destructive' : undefined}>
            {fmtMoney(o.credit.outstanding)} {o.credit.limit !== null ? `sur ${fmtMoney(o.credit.limit)} autorisés` : '(sans limite)'}
          </p>
          <p className="text-xs text-muted-foreground">Commandes confirmées non soldées, TTC.</p>
        </InfoCard>
      </div>
      <SalesLinesTable
        lines={o.lines}
        order
        editable={canManage && draft}
        onAdd={() => setEditing('new')}
        onEdit={(l) => setEditing(l)}
        onDelete={(l) => window.confirm(`Supprimer la ligne ${l.line_no} ?`) && removeLine.mutate(l)}
      />
      <div className="mt-4">
        <DocTotals doc={o} />
      </div>
      {o.deliveries.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-semibold">Livraisons</h2>
          <div className="space-y-3">
            {o.deliveries.map((d) => (
              <div key={d.id} className="rounded-xl border bg-card p-4 shadow-xs">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm">
                    <span className="font-mono font-medium">{d.number}</span> · {fmtDate(d.delivered_on)}
                    {d.carrier && ` · ${d.carrier}`}
                  </p>
                  <Button variant="outline" size="sm" onClick={() => pdf.mutate(d.id)}>
                    <FileDown /> Bon de livraison
                  </Button>
                </div>
                <ul className="text-sm text-muted-foreground">
                  {d.lines.map((x, i) => (
                    <li key={i}>
                      {fmtQty(x.quantity)} × {x.designation}
                      {x.dot && <span className="ml-1 font-mono text-xs">· DOT {x.dot}</span>}
                      {x.location_code && <span className="ml-1 font-mono text-xs">· {x.location_code}</span>}
                    </li>
                  ))}
                </ul>
                {d.note && <p className="mt-1 text-xs italic">{d.note}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
      {editing && (
        <LineDialog line={editing === 'new' ? null : (editing as OrderLine)} customerId={o.customer.id} siteId={o.site.id} withDot onSave={saveLine} onClose={() => setEditing(null)} />
      )}
      {dialog === 'deliver' && <DeliverDialog order={o} onDone={done} onClose={() => setDialog(null)} />}
      {dialog === 'cancel' && (
        <ReasonDialog<Order> title="Annuler la commande" description="Les réservations de stock sont libérées." confirm="Annuler la commande" path={`/sales/orders/${id}/cancel`} onDone={done} onClose={() => setDialog(null)} />
      )}
      {dialog === 'close' && (
        <ReasonDialog<Order> title="Solder le reliquat" description="Ce qui reste à livrer est abandonné et le stock réservé est libéré." confirm="Solder" path={`/sales/orders/${id}/close`} onDone={done} onClose={() => setDialog(null)} />
      )}
      {credit && <CreditDialog message={credit} pending={confirm.isPending} onForce={() => confirm.mutate(true)} onClose={() => setCredit(null)} />}
    </>
  )
}

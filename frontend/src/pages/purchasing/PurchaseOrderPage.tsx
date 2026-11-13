import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ClipboardCheck,
  EllipsisVertical,
  FileText,
  LoaderCircle,
  PackageCheck,
  Send,
  ShieldCheck,
  Trash2,
  Truck,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api, ApiError, openFile } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { LinesEditor } from '@/pages/purchasing/LinesEditor'
import { AckDialog, ReasonDialog, ReceiveDialog } from '@/pages/purchasing/OrderDialogs'
import { formatDate, money, ORDER_STATUSES, orderTitle, qty, type Order, type Site } from '@/pages/purchasing/types'

type DialogKind = 'reject' | 'cancel' | 'close' | 'ack' | 'receive' | null

function Card({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn('rounded-xl border bg-card p-5 shadow-xs', className)}>
      <h2 className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h2>
      {children}
    </section>
  )
}

export function PurchaseOrderPage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<DialogKind>(null)
  const canManage = can(me?.permissions, 'purchasing:manage')
  const canApprove = can(me?.permissions, 'purchasing:approve')
  const key = ['purchase-order', company?.id, Number(id)]

  const order = useQuery({
    queryKey: key,
    queryFn: () => api<Order>(`/purchasing/orders/${id}`),
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  })
  const sites = useQuery({ queryKey: ['sites', company?.id, 'active'], queryFn: () => api<Site[]>('/org/sites?active=true') })
  const update = (o: Order) => {
    queryClient.setQueryData(key, o)
    void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] })
  }
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api<Order>(`/purchasing/orders/${id}/${path}`, { method: 'POST', body }),
    onSuccess: update,
  })
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Order>(`/purchasing/orders/${id}`, { method: 'PATCH', body: { ...body, version: order.data!.version } }),
    onSuccess: update,
  })
  const remove = useMutation({
    mutationFn: () => api<void>(`/purchasing/orders/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['purchase-orders'] })
      navigate('/achats', { replace: true })
    },
  })
  const pdf = useMutation({ mutationFn: () => openFile(`/purchasing/orders/${id}/pdf`) })

  const back = (
    <Link to="/achats" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Commandes fournisseur
    </Link>
  )
  if (order.isPending) return <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
  if (order.isError) return <div className="space-y-4">{back}<ErrorAlert error={order.error} /></div>
  const o = order.data
  const st = ORDER_STATUSES[o.status]
  const draft = o.status === 'brouillon'
  const inProgress = ['envoyee', 'confirmee', 'partielle'].includes(o.status)
  const busy = action.isPending
  const run = (path: string, body?: unknown) => action.mutate({ path, body })
  const overThreshold = o.approval_threshold !== null && Number(o.total_ht) > Number(o.approval_threshold)

  return (
    <>
      {back}
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            <span className={cn(!o.number && 'text-muted-foreground')}>{orderTitle(o)}</span>
            <Badge variant={st.variant}>{st.label}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/fournisseurs/${o.supplier.id}`} className="font-medium text-foreground hover:underline">
              {o.supplier.name}
            </Link>{' '}
            · {money(o.total_ht)} HT · {o.lines.length} ligne{o.lines.length > 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {o.number && (
            <Button variant="outline" disabled={pdf.isPending} onClick={() => pdf.mutate()}>
              {pdf.isPending ? <LoaderCircle className="animate-spin" /> : <FileText />} Bon de commande PDF
            </Button>
          )}
          {canManage && draft && (
            <Button disabled={busy || !o.lines.length} onClick={() => run('submit', { version: o.version })}>
              <Check /> {overThreshold && !canApprove ? 'Demander la validation' : 'Valider la commande'}
            </Button>
          )}
          {o.status === 'a_valider' && canApprove && (
            <>
              <Button variant="outline" disabled={busy} onClick={() => setDialog('reject')}>
                <X /> Refuser
              </Button>
              <Button disabled={busy} onClick={() => run('approve', { version: o.version })}>
                <ShieldCheck /> Approuver
              </Button>
            </>
          )}
          {canManage && o.status === 'validee' && (
            <Button disabled={busy} onClick={() => run('send')}>
              <Send /> Marquer envoyée
            </Button>
          )}
          {canManage && inProgress && (
            <>
              <Button variant="outline" onClick={() => setDialog('ack')}>
                <ClipboardCheck /> Accusé fournisseur
              </Button>
              <Button onClick={() => setDialog('receive')}>
                <PackageCheck /> Réceptionner
              </Button>
            </>
          )}
          {canManage && (draft || ['a_valider', 'validee', 'envoyee', 'confirmee', 'partielle'].includes(o.status)) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" aria-label="Autres actions">
                  <EllipsisVertical />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {draft && (
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => window.confirm('Supprimer ce brouillon ?') && remove.mutate()}>
                    <Trash2 /> Supprimer le brouillon
                  </DropdownMenuItem>
                )}
                {['a_valider', 'validee', 'envoyee', 'confirmee'].includes(o.status) && (
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDialog('cancel')}>
                    <X /> Annuler la commande
                  </DropdownMenuItem>
                )}
                {o.status === 'partielle' && (
                  <DropdownMenuItem onSelect={() => setDialog('close')}>
                    <Check /> Clôturer (abandonner le reliquat)
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <ErrorAlert error={action.error ?? patch.error ?? remove.error ?? pdf.error} />
        {draft && o.rejection_reason && (
          <Banner tone="destructive" icon={<X className="size-4" />}>
            Validation refusée : {o.rejection_reason}
          </Banner>
        )}
        {o.status === 'a_valider' && (
          <Banner tone="accent" icon={<ShieldCheck className="size-4" />}>
            En attente d'approbation : le montant dépasse le seuil de {money(o.approval_threshold)} HT.
            {!canApprove && ' Une personne ayant le droit « valider les achats » doit l’approuver.'}
          </Banner>
        )}
        {o.status === 'validee' && (
          <Banner tone="accent" icon={<Send className="size-4" />}>
            Commande validée : téléchargez le bon de commande, envoyez-le au fournisseur{o.supplier.email && ` (${o.supplier.email})`}, puis marquez-la envoyée.
          </Banner>
        )}
        {(o.status === 'annulee' || o.status === 'cloturee') && o.cancel_reason && (
          <Banner tone="muted" icon={<X className="size-4" />}>
            {o.status === 'annulee' ? 'Annulée' : 'Clôturée'} : {o.cancel_reason}
          </Banner>
        )}
        {o.warnings.map((w) => (
          <Banner key={w} tone="warning" icon={<AlertTriangle className="size-4" />}>
            {w}
          </Banner>
        ))}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Fournisseur">
          <p className="font-medium">{o.supplier.name}</p>
          <p className="text-sm whitespace-pre-line text-muted-foreground">{o.supplier.order_address.join('\n') || 'Pas d’adresse de commande'}</p>
          <dl className="mt-3 space-y-1 text-sm">
            <Info label="Règlement">{o.supplier.payment_terms}</Info>
            <Info label="Franco">{o.supplier.free_shipping_amount && money(o.supplier.free_shipping_amount)}</Info>
            <Info label="Délai habituel">{o.supplier.lead_time_days !== null && `${o.supplier.lead_time_days} j`}</Info>
          </dl>
        </Card>
        <Card title="Livraison">
          {draft && canManage ? (
            <NativeSelect aria-label="Dépôt de livraison" value={o.site.id} onChange={(e) => patch.mutate({ site_id: Number(e.target.value) })}>
              {sites.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — {s.city}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <p className="flex items-center gap-2 font-medium">
              <Truck className="size-4 text-muted-foreground" /> {o.site.name} — {o.site.city}
            </p>
          )}
          <label className="mt-3 grid gap-1 text-sm">
            <span className="text-muted-foreground">Livraison souhaitée le</span>
            <Input
              type="date"
              disabled={!canManage || ['recue', 'cloturee', 'annulee'].includes(o.status)}
              defaultValue={o.expected_date ?? ''}
              key={`exp-${o.version}`}
              onBlur={(e) => e.target.value !== (o.expected_date ?? '') && patch.mutate({ expected_date: e.target.value || null })}
            />
          </label>
        </Card>
        <Card title="Suivi">
          <dl className="space-y-1 text-sm">
            <Info label="Créée">{formatDateTime(o.created_at)}</Info>
            <Info label="Validée">{o.order_date && formatDate(o.order_date)}</Info>
            <Info label="Approuvée">{o.approved_at && formatDateTime(o.approved_at)}</Info>
            <Info label="Envoyée">{o.sent_at && formatDateTime(o.sent_at)}</Info>
            <Info label="Accusé">{o.confirmed_at && `${formatDateTime(o.confirmed_at)}${o.supplier_reference ? ` · n° ${o.supplier_reference}` : ''}`}</Info>
          </dl>
        </Card>
      </div>

      <section className="mt-6">
        <h2 className="mb-3 text-lg font-semibold">Lignes</h2>
        {draft && canManage ? <LinesEditor order={o} onChange={update} /> : <LinesView order={o} />}
      </section>

      {draft && canManage && (
        <label className="mt-6 grid max-w-3xl gap-1 text-sm">
          <span className="font-medium">Note pour le fournisseur (imprimée sur le bon de commande)</span>
          <Textarea rows={2} defaultValue={o.supplier_note ?? ''} key={`sn-${o.version}`} onBlur={(e) => e.target.value !== (o.supplier_note ?? '') && patch.mutate({ supplier_note: e.target.value || null })} />
        </label>
      )}
      <label className="mt-4 grid max-w-3xl gap-1 text-sm">
        <span className="font-medium">Note interne</span>
        <Textarea rows={2} disabled={!canManage} defaultValue={o.internal_note ?? ''} key={`in-${o.version}`} onBlur={(e) => e.target.value !== (o.internal_note ?? '') && patch.mutate({ internal_note: e.target.value || null })} />
      </label>

      {o.receptions.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-3 text-lg font-semibold">Réceptions</h2>
          <div className="space-y-2">
            {o.receptions.map((r) => (
              <div key={r.id} className="rounded-xl border bg-card p-4 text-sm shadow-xs">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  <PackageCheck className="size-4 text-emerald-600" />
                  <span className="font-mono">{r.number}</span> · reçue le {formatDate(r.received_on)}
                  {r.delivery_note && <span className="text-muted-foreground">· BL {r.delivery_note}</span>}
                </p>
                <ul className="mt-1 text-muted-foreground">
                  {r.lines.map((rl, i) => {
                    const line = o.lines.find((l) => l.id === rl.order_line_id)
                    return (
                      <li key={i}>
                        {qty(rl.quantity)} × {line?.designation}
                        {rl.dot && <span className="ml-1 font-mono text-xs">· DOT {rl.dot}</span>}
                      </li>
                    )
                  })}
                </ul>
                {r.note && <p className="mt-1 text-xs italic">{r.note}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {dialog === 'reject' && (
        <ReasonDialog title="Refuser la commande" description="Elle repasse en brouillon ; le demandeur verra votre motif." label="Motif du refus" confirm="Refuser" path={`/purchasing/orders/${o.id}/reject`} onDone={update} onClose={() => setDialog(null)} />
      )}
      {dialog === 'cancel' && (
        <ReasonDialog title="Annuler la commande" description="Pensez à prévenir le fournisseur si elle lui a été envoyée." label="Motif" confirm="Annuler la commande" destructive path={`/purchasing/orders/${o.id}/cancel`} onDone={update} onClose={() => setDialog(null)} />
      )}
      {dialog === 'close' && (
        <ReasonDialog title="Clôturer la commande" description="Le reliquat ne sera plus attendu." label="Motif (rupture définitive…)" confirm="Clôturer" path={`/purchasing/orders/${o.id}/close`} onDone={update} onClose={() => setDialog(null)} />
      )}
      {dialog === 'ack' && <AckDialog order={o} onDone={update} onClose={() => setDialog(null)} />}
      {dialog === 'receive' && <ReceiveDialog order={o} onDone={update} onClose={() => setDialog(null)} />}
    </>
  )
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children || '—'}</dd>
    </div>
  )
}

function Banner({ tone, icon, children }: { tone: 'warning' | 'accent' | 'destructive' | 'muted'; icon: ReactNode; children: ReactNode }) {
  const styles = {
    warning: 'border-amber-500/40 bg-amber-500/10 text-amber-900',
    accent: 'border-sky-500/30 bg-sky-500/10 text-sky-900',
    destructive: 'border-destructive/40 bg-destructive/5 text-destructive',
    muted: 'bg-secondary/50 text-muted-foreground',
  }
  return (
    <div className={cn('flex items-start gap-2 rounded-lg border px-3 py-2 text-sm', styles[tone])}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span>{children}</span>
    </div>
  )
}

function LinesView({ order }: { order: Order }) {
  const tracking = !['brouillon', 'a_valider', 'validee', 'annulee'].includes(order.status)
  return (
    <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
      <table className="w-full text-sm">
        <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-10 px-3 py-2.5 font-medium">#</th>
            <th className="px-3 py-2.5 font-medium">Désignation</th>
            <th className="px-3 py-2.5 text-right font-medium">Qté</th>
            <th className="px-3 py-2.5 text-right font-medium">P.U. HT</th>
            <th className="hidden px-3 py-2.5 text-right font-medium md:table-cell">Total HT</th>
            {tracking && (
              <>
                <th className="px-3 py-2.5 text-right font-medium">Confirmé</th>
                <th className="px-3 py-2.5 text-right font-medium">Reçu</th>
                <th className="px-3 py-2.5 text-right font-medium">Reste</th>
              </>
            )}
          </tr>
        </thead>
        <tbody className="divide-y">
          {order.lines.map((l) => {
            const rest = Math.max(0, Number(l.quantity) - Number(l.received_qty))
            const short = l.confirmed_qty !== null && Number(l.confirmed_qty) < Number(l.quantity)
            return (
              <tr key={l.id}>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{l.line_no}</td>
                <td className="px-3 py-2.5">
                  <p className="font-medium">
                    {l.article_id ? (
                      <Link to={`/articles/${l.article_id}`} className="hover:underline">
                        {l.designation}
                      </Link>
                    ) : (
                      l.designation
                    )}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground">{l.supplier_ref}</p>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{qty(l.quantity)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {money(l.unit_price)}
                  {Number(l.discount_pct) > 0 && <span className="block text-xs text-muted-foreground">−{qty(l.discount_pct)} %</span>}
                </td>
                <td className="hidden px-3 py-2.5 text-right font-medium tabular-nums md:table-cell">{money(l.line_total)}</td>
                {tracking && (
                  <>
                    <td className={cn('px-3 py-2.5 text-right tabular-nums', short && 'font-medium text-amber-700')}>
                      {l.confirmed_qty !== null ? qty(l.confirmed_qty) : '—'}
                      {l.confirmed_date && <span className="block text-xs text-muted-foreground">{formatDate(l.confirmed_date)}</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{qty(l.received_qty)}</td>
                    <td className={cn('px-3 py-2.5 text-right tabular-nums', rest > 0 ? 'font-medium' : 'text-emerald-700')}>{rest > 0 ? qty(rest) : '✓'}</td>
                  </>
                )}
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="border-t bg-secondary/30">
            <td colSpan={4} className="px-3 py-2.5 text-right font-medium">
              Total HT
            </td>
            <td className="hidden px-3 py-2.5 text-right font-semibold tabular-nums md:table-cell">{money(order.total_ht)}</td>
            {tracking && <td colSpan={3} />}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

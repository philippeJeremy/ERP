import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, FileDown, LoaderCircle, RotateCcw, Send, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api, ApiError, openFile } from '@/lib/api'
import { can } from '@/lib/permissions'
import { CreditDialog, ReasonDialog } from '@/pages/sales/dialogs'
import { LineDialog, type LineBody } from '@/pages/sales/LineDialog'
import { DocTotals, InfoCard, SalesLinesTable } from '@/pages/sales/parts'
import { fmtDate, QUOTE_STATUSES, type Order, type Quote, type SalesLine } from '@/pages/sales/types'

export function QuotePage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'sales:manage')
  const [editing, setEditing] = useState<SalesLine | 'new' | null>(null)
  const [refusing, setRefusing] = useState(false)
  const [credit, setCredit] = useState<string | null>(null)
  const key = ['quote', company?.id, Number(id)]
  const quote = useQuery({ queryKey: key, queryFn: () => api<Quote>(`/sales/quotes/${id}`) })
  const done = (q: Quote) => {
    queryClient.setQueryData(key, q)
    void queryClient.invalidateQueries({ queryKey: ['quotes'] })
  }
  const action = useMutation({
    mutationFn: (path: string) => api<Quote>(`/sales/quotes/${id}/${path}`, { method: 'POST' }),
    onSuccess: done,
  })
  const accept = useMutation({
    mutationFn: (force: boolean) => api<Order>(`/sales/quotes/${id}/accept`, { method: 'POST', body: { version: quote.data!.version, force } }),
    onSuccess: (order) => {
      void queryClient.invalidateQueries({ queryKey: ['quotes'] })
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      navigate(`/ventes/commandes/${order.id}`)
    },
    onError: (e) => e instanceof ApiError && e.code === 'encours_depasse' && setCredit(e.message),
  })
  const removeLine = useMutation({
    mutationFn: (l: SalesLine) => api<Quote>(`/sales/quotes/${id}/lines/${l.id}`, { method: 'DELETE' }),
    onSuccess: done,
  })
  const pdf = useMutation({ mutationFn: () => openFile(`/sales/quotes/${id}/pdf`) })
  const q = quote.data
  if (!q) return quote.isPending ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <ErrorAlert error={quote.error} />
  const status = QUOTE_STATUSES[q.status]
  const draft = q.status === 'brouillon'
  const open = draft || q.status === 'envoye'
  const saveLine = (body: LineBody) =>
    api<Quote>(editing === 'new' ? `/sales/quotes/${id}/lines` : `/sales/quotes/${id}/lines/${(editing as SalesLine).id}`, {
      method: editing === 'new' ? 'POST' : 'PUT',
      body,
    }).then(done)
  return (
    <>
      <Link to="/ventes" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Ventes
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold">
            Devis <span className="font-mono">{q.number}</span>
            <Badge variant={status.variant}>{status.label}</Badge>
            {q.expired && <Badge variant="destructive">Expiré</Badge>}
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/clients/${q.customer.id}`} className="hover:underline">
              {q.customer.name}
            </Link>{' '}
            · du {fmtDate(q.quote_date)}, valable jusqu'au {fmtDate(q.valid_until)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={pdf.isPending} onClick={() => pdf.mutate()}>
            <FileDown /> PDF
          </Button>
          {canManage && draft && (
            <Button variant="outline" disabled={!q.lines.length || action.isPending} onClick={() => action.mutate('send')}>
              <Send /> Marquer envoyé
            </Button>
          )}
          {canManage && (q.status === 'envoye' || q.status === 'refuse') && (
            <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate('reopen')}>
              <RotateCcw /> Rouvrir
            </Button>
          )}
          {canManage && open && (
            <>
              <Button variant="outline" onClick={() => setRefusing(true)}>
                <X /> Refusé
              </Button>
              <Button variant="ghost" disabled={action.isPending} onClick={() => window.confirm('Annuler ce devis ?') && action.mutate('cancel')}>
                <XCircle /> Annuler
              </Button>
              <Button disabled={!q.lines.length || accept.isPending} onClick={() => accept.mutate(false)}>
                {accept.isPending ? <LoaderCircle className="animate-spin" /> : <Check />}
                Accepté → commande
              </Button>
            </>
          )}
          {q.order && (
            <Button asChild>
              <Link to={`/ventes/commandes/${q.order.id}`}>Commande {q.order.number}</Link>
            </Button>
          )}
        </div>
      </div>
      <ErrorAlert error={action.error ?? (accept.error instanceof ApiError && accept.error.code === 'encours_depasse' ? null : accept.error) ?? pdf.error ?? removeLine.error} />
      {q.refusal_reason && <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">Refusé : {q.refusal_reason}</p>}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <InfoCard title="Client">
          <p className="font-medium">{q.customer.name}</p>
          {q.customer.billing_address.map((x) => (
            <p key={x} className="text-muted-foreground">
              {x}
            </p>
          ))}
          {q.customer.vehicle_registration && <p className="font-mono text-xs">Véhicule {q.customer.vehicle_registration}</p>}
        </InfoCard>
        <InfoCard title="Conditions">
          <p>Règlement : {q.customer.payment_terms ?? '—'}</p>
          <p>Dépôt : {q.site.name}</p>
          {q.customer_reference && <p>Réf. client : {q.customer_reference}</p>}
        </InfoCard>
        <InfoCard title="Suivi">
          <p>Créé le {fmtDate(q.created_at.slice(0, 10))}</p>
          {q.sent_at && <p>Envoyé le {fmtDate(q.sent_at.slice(0, 10))}</p>}
          {q.decided_at && <p>Décision le {fmtDate(q.decided_at.slice(0, 10))}</p>}
        </InfoCard>
      </div>
      <SalesLinesTable
        lines={q.lines}
        editable={canManage && draft}
        onAdd={() => setEditing('new')}
        onEdit={(l) => setEditing(l)}
        onDelete={(l) => window.confirm(`Supprimer la ligne ${l.line_no} ?`) && removeLine.mutate(l)}
      />
      {canManage && q.status === 'envoye' && <p className="mt-2 text-xs text-muted-foreground">Pour modifier les lignes d'un devis envoyé, rouvrez-le.</p>}
      <div className="mt-4">
        <DocTotals doc={q} />
      </div>
      {editing && (
        <LineDialog line={editing === 'new' ? null : editing} customerId={q.customer.id} siteId={q.site.id} withDot={false} onSave={saveLine} onClose={() => setEditing(null)} />
      )}
      {refusing && (
        <ReasonDialog<Quote> title="Devis refusé" description="Notez la raison : utile pour suivre vos devis perdus." confirm="Enregistrer le refus" path={`/sales/quotes/${id}/refuse`} onDone={done} onClose={() => setRefusing(false)} />
      )}
      {credit && <CreditDialog message={credit} pending={accept.isPending} onForce={() => accept.mutate(true)} onClose={() => setCredit(null)} />}
    </>
  )
}

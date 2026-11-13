import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Banknote, FileCode2, FileDown, LoaderCircle, Mail, Plus, Send, Trash2, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api, downloadFile, openFile } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { EmailDialog } from '@/pages/mail/EmailDialog'
import { ApplyCreditDialog, CreditNoteDialog, FreeLineDialog, PaymentDialog } from '@/pages/billing/dialogs'
import { statusOf, type Invoice } from '@/pages/billing/types'
import { fmtMoney, fmtQty } from '@/pages/inventory/types'
import { InfoCard } from '@/pages/sales/parts'
import { fmtDate, fmtPct } from '@/pages/sales/types'

export function InvoicePage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'billing:manage')
  const canPay = can(me?.permissions, 'billing:payments')
  const [dialog, setDialog] = useState<'line' | 'credit' | 'pay' | 'apply' | 'mail' | null>(null)
  const key = ['invoice', company?.id, Number(id)]
  const invoice = useQuery({ queryKey: key, queryFn: () => api<Invoice>(`/billing/invoices/${id}`) })
  const refresh = (i?: Invoice) => {
    if (i) queryClient.setQueryData(key, i)
    else void queryClient.invalidateQueries({ queryKey: key })
    void queryClient.invalidateQueries({ queryKey: ['invoices'] })
    void queryClient.invalidateQueries({ queryKey: ['to-invoice'] })
  }
  const issue = useMutation({ mutationFn: () => api<Invoice>(`/billing/invoices/${id}/issue`, { method: 'POST' }), onSuccess: refresh })
  const remove = useMutation({
    mutationFn: () => api<void>(`/billing/invoices/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      refresh()
      navigate('/facturation?vue=factures', { replace: true })
    },
  })
  const removeLine = useMutation({ mutationFn: (lineId: number) => api<Invoice>(`/billing/invoices/${id}/lines/${lineId}`, { method: 'DELETE' }), onSuccess: refresh })
  const unallocate = useMutation({ mutationFn: (allocationId: number) => api<void>(`/billing/allocations/${allocationId}`, { method: 'DELETE' }), onSuccess: () => refresh() })
  const pdf = useMutation({ mutationFn: () => openFile(`/billing/invoices/${id}/pdf`) })
  const xml = useMutation({ mutationFn: () => downloadFile(`/billing/invoices/${id}/xml`, `${invoice.data?.number}.xml`) })
  const inv = invoice.data
  if (!inv) return invoice.isPending ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <ErrorAlert error={invoice.error} />
  const draft = inv.status === 'brouillon'
  const st = statusOf(inv.kind, inv.payment_status)
  const title = inv.kind === 'facture' ? 'Facture' : 'Avoir'
  const hasEco = inv.lines.some((l) => Number(l.eco_fee))
  const hasDiscount = inv.lines.some((l) => Number(l.discount_pct))
  return (
    <>
      <Link to="/facturation?vue=factures" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Factures
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold">
            {title} <span className="font-mono">{inv.number ?? '(brouillon)'}</span>
            <Badge variant={st.variant}>{st.label}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/clients/${inv.customer_id}`} className="hover:underline">
              {inv.customer_name}
            </Link>
            {inv.issue_date && ` · émise le ${fmtDate(inv.issue_date)}`}
            {inv.sent_at && ` · envoyée par mail le ${formatDateTime(inv.sent_at)}`}
            {inv.original && (
              <>
                {' '}
                · sur la facture{' '}
                <Link to={`/facturation/factures/${inv.original.id}`} className="font-mono hover:underline">
                  {inv.original.number}
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={pdf.isPending} onClick={() => pdf.mutate()}>
            <FileDown /> PDF{!draft && ' Factur-X'}
          </Button>
          {!draft && (
            <Button variant="outline" disabled={xml.isPending} onClick={() => xml.mutate()} title="Le XML CII embarqué dans le PDF">
              <FileCode2 /> XML
            </Button>
          )}
          {canManage && !draft && (
            <Button variant="outline" onClick={() => setDialog('mail')}>
              <Mail /> {inv.sent_at ? 'Renvoyer par mail' : 'Envoyer par mail'}
            </Button>
          )}
          {canManage && draft && (
            <>
              <Button variant="ghost" disabled={remove.isPending} onClick={() => window.confirm('Supprimer ce brouillon ?') && remove.mutate()}>
                <Trash2 /> Supprimer
              </Button>
              <Button disabled={!inv.lines.length || issue.isPending} onClick={() => window.confirm(`Émettre ${inv.kind === 'facture' ? 'la facture' : "l'avoir"} ? Elle ne pourra plus être modifiée.`) && issue.mutate()}>
                {issue.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
                Émettre
              </Button>
            </>
          )}
          {canManage && !draft && inv.kind === 'facture' && inv.lines.some((l) => Number(l.creditable_qty ?? 0) > 0) && (
            <Button variant="outline" onClick={() => setDialog('credit')}>
              <Undo2 /> Faire un avoir
            </Button>
          )}
          {canPay && !draft && inv.kind === 'facture' && Number(inv.balance) > 0 && (
            <Button onClick={() => setDialog('pay')}>
              <Banknote /> Encaisser
            </Button>
          )}
          {canPay && !draft && inv.kind === 'avoir' && Number(inv.balance) > 0 && (
            <Button onClick={() => setDialog('apply')}>
              <Banknote /> Imputer le crédit
            </Button>
          )}
        </div>
      </div>
      <ErrorAlert error={issue.error ?? remove.error ?? removeLine.error ?? pdf.error ?? xml.error ?? unallocate.error} />
      {dialog === 'mail' && (
        <EmailDialog<Invoice> title={`Envoyer ${inv.kind === 'facture' ? 'la facture' : "l'avoir"} ${inv.number}`} path={`/billing/invoices/${id}/email`} onSent={refresh} onClose={() => setDialog(null)} />
      )}
      {draft && <p className="mb-4 rounded-md bg-secondary px-3 py-2 text-sm">Brouillon : vérifiez les lignes puis émettez. Le numéro définitif est donné à l'émission.</p>}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <InfoCard title={inv.kind === 'facture' ? 'Facturé à' : 'Client'}>
          <p className="font-medium">{inv.customer_name}</p>
          {(inv.customer_address ?? '').split('\n').map((x, i) => (
            <p key={i} className="text-muted-foreground">
              {x}
            </p>
          ))}
          {inv.customer_vat && <p className="font-mono text-xs">TVA {inv.customer_vat}</p>}
        </InfoCard>
        <InfoCard title="Conditions">
          {inv.kind === 'facture' && <p>Règlement : {inv.payment_terms ?? '—'}</p>}
          {inv.due_date && inv.kind === 'facture' && (
            <p className={cn(inv.days_late > 0 && 'font-medium text-destructive')}>
              Échéance : {fmtDate(inv.due_date)}
              {inv.days_late > 0 && ` (${inv.days_late} jours de retard)`}
            </p>
          )}
          {inv.delivery_date && <p>Livraison : {fmtDate(inv.delivery_date)}</p>}
          {inv.deliveries.length > 0 && <p className="text-xs">BL : {inv.deliveries.map((d) => d.number).join(', ')}</p>}
        </InfoCard>
        <InfoCard title="Suivi">
          {inv.issued_at && <p>Émise le {formatDateTime(inv.issued_at)}</p>}
          {inv.reminder_count > 0 && (
            <p>
              {inv.reminder_count} relance{inv.reminder_count > 1 ? 's' : ''}, la dernière le {formatDateTime(inv.last_reminder_at!)}
            </p>
          )}
          {inv.credit_notes.length > 0 && (
            <p>
              Avoirs :{' '}
              {inv.credit_notes.map((n) => (
                <Link key={n.id} to={`/facturation/factures/${n.id}`} className="mr-2 font-mono text-xs hover:underline">
                  {n.number ?? 'brouillon'}
                </Link>
              ))}
            </p>
          )}
          {inv.note && <p className="text-xs italic">{inv.note}</p>}
        </InfoCard>
      </div>
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 font-medium">Désignation</th>
              <th className="px-3 py-2.5 text-right font-medium">Qté</th>
              <th className="px-3 py-2.5 text-right font-medium">P.U. HT</th>
              {hasDiscount && <th className="px-3 py-2.5 text-right font-medium">Remise</th>}
              {hasEco && <th className="px-3 py-2.5 text-right font-medium">Éco</th>}
              <th className="px-3 py-2.5 text-right font-medium">TVA</th>
              <th className="px-3 py-2.5 text-right font-medium">Total HT</th>
              {draft && canManage && <th className="w-12" />}
            </tr>
          </thead>
          <tbody className="divide-y">
            {inv.lines.map((l) => (
              <tr key={l.id}>
                <td className="px-3 py-2.5">
                  <span className="font-medium">{l.designation}</span>
                  <span className="block text-xs text-muted-foreground">
                    {l.article_code && <span className="mr-2 font-mono">{l.article_code}</span>}
                    {l.delivery_number && <span className="font-mono">{l.delivery_number}</span>}
                    {!draft && inv.kind === 'facture' && l.creditable_qty !== null && Number(l.creditable_qty) < Number(l.quantity) && (
                      <span className="ml-2">({fmtQty(Number(l.quantity) - Number(l.creditable_qty))} repris par avoir)</span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtQty(l.quantity)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtMoney(l.unit_price)}</td>
                {hasDiscount && <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{Number(l.discount_pct) ? fmtPct(l.discount_pct) : ''}</td>}
                {hasEco && <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{Number(l.eco_total) ? fmtMoney(l.eco_total) : ''}</td>}
                <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">{fmtPct(l.vat_rate)}</td>
                <td className="px-3 py-2.5 text-right font-medium tabular-nums">{fmtMoney(Number(l.line_total) + Number(l.eco_total))}</td>
                {draft && canManage && (
                  <td className="px-2 py-1.5">
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label={`Supprimer la ligne ${l.line_no}`} onClick={() => removeLine.mutate(l.id)}>
                      <Trash2 />
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {inv.lines.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune ligne.</p>}
        {draft && canManage && (
          <div className="border-t p-3">
            <Button variant="outline" size="sm" onClick={() => setDialog('line')}>
              <Plus /> Ajouter une ligne
            </Button>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          {inv.allocations.length > 0 && (
            <div className="max-w-xl rounded-xl border bg-card p-4 shadow-xs">
              <h3 className="mb-2 text-sm font-semibold">{inv.kind === 'facture' ? 'Règlements et avoirs imputés' : 'Crédit utilisé sur'}</h3>
              <ul className="space-y-1 text-sm">
                {inv.allocations.map((a) => (
                  <li key={a.id} className="flex items-center gap-3">
                    <span className="text-muted-foreground">{fmtDate(a.allocated_on)}</span>
                    <span className="font-mono text-xs">{inv.kind === 'facture' ? a.source_number : a.invoice_number}</span>
                    <Badge variant="outline">{a.source === 'reglement' ? 'Règlement' : 'Avoir'}</Badge>
                    <span className="ml-auto tabular-nums">{fmtMoney(a.amount)}</span>
                    {canPay && (
                      <button type="button" className="text-xs text-muted-foreground hover:text-destructive" onClick={() => window.confirm('Défaire ce lettrage ?') && unallocate.mutate(a.id)}>
                        défaire
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="w-full max-w-sm space-y-1.5 rounded-xl border bg-card p-4 text-sm shadow-xs">
          <Row label="Total HT" value={fmtMoney(inv.total_ht)} />
          {Number(inv.total_eco) > 0 && <Row label="dont éco-contribution" value={fmtMoney(inv.total_eco)} muted />}
          {inv.vat.map((v) => (
            <Row key={v.rate} label={`TVA ${fmtPct(v.rate)}`} value={fmtMoney(v.vat)} muted />
          ))}
          <div className="border-t pt-1.5">
            <Row label="Total TTC" value={fmtMoney(inv.total_ttc)} strong />
          </div>
          {!draft && (
            <>
              <Row label={inv.kind === 'facture' ? 'Réglé' : 'Crédit utilisé'} value={fmtMoney(inv.paid_amount)} muted />
              <Row label={inv.kind === 'facture' ? 'Reste dû' : 'Crédit disponible'} value={fmtMoney(inv.balance)} strong />
            </>
          )}
        </div>
      </div>
      {dialog === 'line' && <FreeLineDialog invoiceId={inv.id} onDone={refresh} onClose={() => setDialog(null)} />}
      {dialog === 'credit' && <CreditNoteDialog invoice={inv} onDone={(note) => navigate(`/facturation/factures/${note.id}`)} onClose={() => setDialog(null)} />}
      {dialog === 'pay' && <PaymentDialog customerId={inv.customer_id} invoice={inv} onDone={() => refresh()} onClose={() => setDialog(null)} />}
      {dialog === 'apply' && <ApplyCreditDialog note={inv} onDone={() => refresh()} onClose={() => setDialog(null)} />}
    </>
  )
}

function Row({ label, value, muted, strong }: { label: string; value: string; muted?: boolean; strong?: boolean }) {
  return (
    <div className={cn('flex justify-between', muted && 'text-muted-foreground', strong && 'text-base font-semibold')}>
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, CircleCheck, LoaderCircle, Mail } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api, openFile } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { AgingRow } from '@/pages/billing/types'
import { fmtMoney } from '@/pages/inventory/types'
import { EmailDialog } from '@/pages/mail/EmailDialog'

/** Balance âgée : ce que doit chaque client, par ancienneté du retard ; relance en un clic. */
export function ReceivablesTab() {
  const { me, company } = useAuth()
  const queryClient = useQueryClient()
  const canPay = can(me?.permissions, 'billing:payments')
  const [mailTo, setMailTo] = useState<AgingRow | null>(null)
  const data = useQuery({ queryKey: ['receivables', company?.id], queryFn: () => api<{ rows: AgingRow[]; totals: AgingRow }>('/billing/receivables') })
  const reminded = () => {
    void queryClient.invalidateQueries({ queryKey: ['receivables'] })
    void queryClient.invalidateQueries({ queryKey: ['invoices'] })
  }
  const remind = useMutation({
    mutationFn: (customerId: number) => openFile(`/billing/customers/${customerId}/reminder`, 'POST'),
    onSuccess: reminded,
  })
  const t = data.data?.totals
  const cell = (v: string, danger = false) => <td className={cn('px-4 py-3 text-right tabular-nums', Number(v) ? (danger ? 'font-medium text-destructive' : '') : 'text-muted-foreground')}>{Number(v) ? fmtMoney(v) : '—'}</td>
  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">
        Factures émises non soldées, par client et par ancienneté du retard. « Lettre » ou « Mail » note la relance sur chaque facture en retard (1re relance, 2e relance, puis mise en demeure) : la lettre s'ouvre en PDF, le mail
        part avec les factures jointes.
      </p>
      <ErrorAlert error={data.error ?? remind.error} />
      {mailTo && <EmailDialog title={`Relancer ${mailTo.customer_name}`} path={`/billing/customers/${mailTo.customer_id}/reminder-email`} onSent={reminded} onClose={() => setMailTo(null)} />}
      {data.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {data.data && data.data.rows.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border bg-card py-12 text-center shadow-xs">
          <CircleCheck className="size-8 text-emerald-600" />
          <p className="font-medium">Aucune créance en cours</p>
        </div>
      )}
      {data.data && data.data.rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
          <table className="w-full text-sm">
            <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Client</th>
                <th className="px-4 py-2.5 text-right font-medium">Non échu</th>
                <th className="px-4 py-2.5 text-right font-medium">1-30 j</th>
                <th className="px-4 py-2.5 text-right font-medium">31-60 j</th>
                <th className="px-4 py-2.5 text-right font-medium">+60 j</th>
                <th className="px-4 py-2.5 text-right font-medium">Total dû</th>
                <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Dernière relance</th>
                {canPay && <th className="w-48" />}
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.data.rows.map((r) => {
                const late = Number(r.late_30) + Number(r.late_60) + Number(r.late_more) > 0
                return (
                  <tr key={r.customer_id}>
                    <td className="px-4 py-3">
                      <Link to={`/facturation?vue=factures&q=${encodeURIComponent(r.customer_name)}`} className="font-medium hover:underline">
                        {r.customer_name}
                      </Link>
                    </td>
                    {cell(r.not_due)}
                    {cell(r.late_30, true)}
                    {cell(r.late_60, true)}
                    {cell(r.late_more, true)}
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{fmtMoney(r.total)}</td>
                    <td className="hidden px-4 py-3 text-xs text-muted-foreground lg:table-cell">{r.last_reminder_at ? formatDateTime(r.last_reminder_at) : '—'}</td>
                    {canPay && (
                      <td className="px-2 py-1.5 text-right">
                        {late && (
                          <div className="flex justify-end gap-1.5">
                            <Button size="sm" variant="outline" disabled={remind.isPending} onClick={() => remind.mutate(r.customer_id)} title="Relance par courrier (PDF)">
                              <BellRing /> Lettre
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setMailTo(r)} title="Relance par e-mail">
                              <Mail /> Mail
                            </Button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
            {t && (
              <tfoot className="border-t bg-secondary/30 font-medium">
                <tr>
                  <td className="px-4 py-3">Total</td>
                  {cell(t.not_due)}
                  {cell(t.late_30, true)}
                  {cell(t.late_60, true)}
                  {cell(t.late_more, true)}
                  <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(t.total)}</td>
                  <td className="hidden lg:table-cell" />
                  {canPay && <td />}
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </>
  )
}

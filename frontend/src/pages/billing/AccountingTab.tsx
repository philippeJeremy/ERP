import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api, downloadFile } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { BillingSettings, Entry } from '@/pages/billing/types'
import { fmtMoney } from '@/pages/inventory/types'
import { fmtDate } from '@/pages/sales/types'

const firstOfMonth = () => {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}
const todayIso = () => new Date().toISOString().slice(0, 10)

const ACCOUNTS: [keyof BillingSettings, string][] = [
  ['customer_account', 'Clients'],
  ['supplier_account', 'Fournisseurs'],
  ['sales_goods_account', 'Ventes de marchandises'],
  ['sales_services_account', 'Prestations de services'],
  ['eco_fee_account', 'Éco-contributions'],
  ['vat_collected_account', 'TVA collectée'],
  ['purchases_account', 'Achats de marchandises'],
  ['vat_deductible_account', 'TVA déductible'],
  ['bank_account', 'Banque'],
  ['cash_account', 'Caisse (espèces)'],
  ['sales_journal', 'Journal des ventes'],
  ['purchases_journal', 'Journal des achats'],
  ['bank_journal', 'Journal de banque'],
]

export function AccountingTab() {
  const { company } = useAuth()
  const [start, setStart] = useState(firstOfMonth())
  const [end, setEnd] = useState(todayIso())
  const range = `start=${start}&end=${end}`
  const entries = useQuery({
    queryKey: ['entries', company?.id, range],
    queryFn: () => api<{ entries: Entry[]; total_debit: string; total_credit: string }>(`/billing/accounting/entries?${range}`),
    enabled: !!start && !!end && start <= end,
  })
  const csv = useMutation({ mutationFn: () => downloadFile(`/billing/accounting/export.csv?${range}`, `ecritures-${start}-${end}.csv`) })
  const fec = useMutation({ mutationFn: () => downloadFile(`/billing/accounting/fec?${range}`, `FEC-${end.replaceAll('-', '')}.txt`) })
  const balanced = entries.data && entries.data.total_debit === entries.data.total_credit
  return (
    <div className="space-y-6">
      <section>
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <Field id="acc_start" label="Du">
            <Input id="acc_start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field id="acc_end" label="Au">
            <Input id="acc_end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Button variant="outline" disabled={csv.isPending} onClick={() => csv.mutate()}>
            <Download /> CSV (Excel)
          </Button>
          <Button variant="outline" disabled={fec.isPending} onClick={() => fec.mutate()} title="Fichier des Écritures Comptables, format de l'administration fiscale">
            <Download /> FEC
          </Button>
          {entries.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        </div>
        <p className="mb-3 text-sm text-muted-foreground">
          Écritures générées depuis les factures et avoirs émis, les factures fournisseur validées et les règlements. À importer dans le logiciel de votre expert-comptable.
        </p>
        <ErrorAlert error={entries.error ?? csv.error ?? fec.error} />
        {entries.data && (
          <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
            <table className="w-full text-sm">
              <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Jnl</th>
                  <th className="px-3 py-2 font-medium">Date</th>
                  <th className="px-3 py-2 font-medium">Pièce</th>
                  <th className="px-3 py-2 font-medium">Compte</th>
                  <th className="px-3 py-2 font-medium">Libellé</th>
                  <th className="px-3 py-2 text-right font-medium">Débit</th>
                  <th className="px-3 py-2 text-right font-medium">Crédit</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {entries.data.entries.slice(0, 300).map((e, i) => (
                  <tr key={i}>
                    <td className="px-3 py-1.5 font-mono text-xs">{e.journal}</td>
                    <td className="px-3 py-1.5">{fmtDate(e.date)}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{e.piece}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">
                      {e.account}
                      {e.aux_account && <span className="text-muted-foreground"> · {e.aux_account}</span>}
                    </td>
                    <td className="px-3 py-1.5">{e.label}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{Number(e.debit) ? fmtMoney(e.debit) : ''}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{Number(e.credit) ? fmtMoney(e.credit) : ''}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t bg-secondary/30 font-medium">
                <tr>
                  <td colSpan={5} className={cn('px-3 py-2', balanced ? 'text-emerald-700' : 'text-destructive')}>
                    {entries.data.entries.length} lignes · {balanced ? 'équilibré' : 'déséquilibré !'}
                    {entries.data.entries.length > 300 && ' (300 premières affichées, tout est dans les exports)'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(entries.data.total_debit)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(entries.data.total_credit)}</td>
                </tr>
              </tfoot>
            </table>
            {entries.data.entries.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune écriture sur la période.</p>}
          </div>
        )}
      </section>
      <SettingsForm />
    </div>
  )
}

function SettingsForm() {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['billing-settings', company?.id], queryFn: () => api<BillingSettings>('/billing/settings') })
  const [form, setForm] = useState<BillingSettings | null>(null)
  const values = form ?? settings.data
  const save = useMutation({
    mutationFn: (v: BillingSettings) => api<BillingSettings>('/billing/settings', { method: 'PUT', body: v }),
    onSuccess: (s) => {
      queryClient.setQueryData(['billing-settings', company?.id], s)
      setForm(null)
    },
  })
  if (!values) return null
  return (
    <section className="rounded-xl border bg-card p-5 shadow-xs">
      <h2 className="mb-1 text-lg font-semibold">Réglages comptables</h2>
      <p className="mb-4 text-sm text-muted-foreground">Comptes du plan comptable utilisés dans les exports. Un compte propre à un client ou un fournisseur (sur sa fiche) l'emporte.</p>
      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <Field id="set_days" label="Délai de paiement par défaut (jours)">
          <Input id="set_days" value={String(values.default_payment_days)} onChange={(e) => setForm({ ...values, default_payment_days: Number(e.target.value) || 0 })} />
        </Field>
        <Field id="set_vat" label="TVA par défaut (%)">
          <Input id="set_vat" value={values.default_vat_rate} onChange={(e) => setForm({ ...values, default_vat_rate: e.target.value })} />
        </Field>
        {ACCOUNTS.map(([k, label]) => (
          <Field key={k} id={`set_${k}`} label={label}>
            <Input id={`set_${k}`} className="font-mono" value={String(values[k])} onChange={(e) => setForm({ ...values, [k]: e.target.value.toUpperCase() })} />
          </Field>
        ))}
      </div>
      <ErrorAlert error={save.error} />
      <div className="mt-4 flex justify-end">
        <Button disabled={!form || save.isPending} onClick={() => form && save.mutate(form)}>
          {save.isPending && <LoaderCircle className="animate-spin" />}
          Enregistrer
        </Button>
      </div>
    </section>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Banknote, Building, FileText, History, LoaderCircle, MapPin, Power, ShoppingCart, UsersRound, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { AddressesTab } from '@/pages/partners/AddressesTab'
import { ContactsTab } from '@/pages/partners/ContactsTab'
import { CustomerTermsForm, InfoForm } from '@/pages/partners/SupplierForms'
import { CUSTOMER_KINDS, describeCustomerTerms, formatMoney, partnerDisplayName, type Partner } from '@/pages/partners/types'
import { NewSalesDocDialog } from '@/pages/sales/NewSalesDocDialog'
import { fmtDate, fmtPct, ORDER_STATUSES, QUOTE_STATUSES, type CustomerActivity } from '@/pages/sales/types'

const TABS: { id: string; label: string; icon: LucideIcon }[] = [
  { id: 'informations', label: 'Informations', icon: Building },
  { id: 'adresses', label: 'Adresses', icon: MapPin },
  { id: 'contacts', label: 'Contacts', icon: UsersRound },
  { id: 'conditions', label: 'Conditions de vente', icon: Banknote },
  { id: 'activite', label: 'Devis et commandes', icon: History },
]

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium">{value ?? '—'}</dd>
    </div>
  )
}

export function CustomerPage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState<'quote' | 'order' | null>(null)
  const tab = TABS.find((t) => t.id === params.get('onglet'))?.id ?? 'informations'
  const readOnly = !can(me?.permissions, 'partners:manage')
  const canSell = can(me?.permissions, 'sales:manage')
  const partner = useQuery({ queryKey: ['partner', company?.id, Number(id)], queryFn: () => api<Partner>(`/partners/${id}`) })
  const activity = useQuery({
    queryKey: ['customer-activity', company?.id, Number(id)],
    queryFn: () => api<CustomerActivity>(`/sales/customers/${id}/activity`),
    enabled: can(me?.permissions, 'sales:read') && !!partner.data?.is_customer,
  })
  const toggleActive = useMutation({
    mutationFn: (p: Partner) => api<Partner>(`/partners/${p.id}`, { method: 'PATCH', body: { version: p.version, is_active: !p.is_active } }),
    onSuccess: (saved) => queryClient.setQueryData(['partner', company?.id, saved.id], saved),
  })
  if (partner.isPending) return <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
  if (partner.isError) return <ErrorAlert error={partner.error} />
  const p = partner.data
  const credit = activity.data?.credit
  const discounts = [
    Number(p.discount_pct) ? `${fmtPct(p.discount_pct)} général` : null,
    p.discount_tire_pct !== null ? `${fmtPct(p.discount_tire_pct)} pneus` : null,
  ].filter(Boolean)
  return (
    <>
      <Link to="/clients" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Clients
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {partnerDisplayName(p)}
            <Badge variant="secondary">{CUSTOMER_KINDS[p.customer_kind ?? 'pro']}</Badge>
            {!p.is_active && <Badge variant="outline">Désactivé</Badge>}
          </h1>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono">{p.code}</span>
            {p.vehicle_registration && <span className="ml-2 font-mono">· {p.vehicle_registration}</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canSell && p.is_active && (
            <>
              <Button variant="outline" onClick={() => setCreating('quote')}>
                <FileText /> Nouveau devis
              </Button>
              <Button onClick={() => setCreating('order')}>
                <ShoppingCart /> Nouvelle commande
              </Button>
            </>
          )}
          {!readOnly && (
            <Button variant="outline" size="icon" aria-label={p.is_active ? 'Désactiver' : 'Réactiver'} title={p.is_active ? 'Désactiver' : 'Réactiver'} onClick={() => toggleActive.mutate(p)}>
              <Power />
            </Button>
          )}
        </div>
      </div>
      <dl className="mb-6 grid grid-cols-2 gap-4 rounded-xl border bg-card p-4 shadow-xs sm:grid-cols-4">
        <Fact label="Règlement" value={describeCustomerTerms(p)} />
        <Fact label="Remises" value={discounts.length ? discounts.join(', ') : null} />
        <Fact label="Encours (commandes en cours)" value={credit ? formatMoney(credit.outstanding) : null} />
        <Fact label="Encours autorisé" value={p.credit_limit ? formatMoney(p.credit_limit) : 'Sans limite'} />
      </dl>
      <ErrorAlert error={toggleActive.error} />
      <div role="tablist" className="mb-6 flex gap-1 overflow-x-auto border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setParams(t.id === 'informations' ? {} : { onglet: t.id }, { replace: true })}
            className={cn(
              '-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <t.icon className="size-4" />
            {t.label}
          </button>
        ))}
      </div>
      <div className="rounded-xl border bg-card px-6 pt-6 shadow-xs">
        {tab === 'informations' && <InfoForm partner={p} readOnly={readOnly} role="customer" key={p.customer_kind} />}
        {tab === 'conditions' && <CustomerTermsForm partner={p} readOnly={readOnly} />}
        {tab === 'adresses' && (
          <div className="pb-6">
            <AddressesTab partner={p} readOnly={readOnly} />
          </div>
        )}
        {tab === 'contacts' && (
          <div className="pb-6">
            <ContactsTab partner={p} readOnly={readOnly} />
          </div>
        )}
        {tab === 'activite' && (
          <div className="grid gap-6 pb-6 lg:grid-cols-2">
            <ActivityList
              title="Derniers devis"
              rows={(activity.data?.quotes ?? []).map((x) => ({ id: x.id, to: `/ventes/devis/${x.id}`, number: x.number, date: x.quote_date, total: x.total_ttc, status: QUOTE_STATUSES[x.status] }))}
            />
            <ActivityList
              title="Dernières commandes"
              rows={(activity.data?.orders ?? []).map((x) => ({ id: x.id, to: `/ventes/commandes/${x.id}`, number: x.number, date: x.order_date, total: x.total_ttc, status: ORDER_STATUSES[x.status] }))}
            />
          </div>
        )}
      </div>
      {creating && <NewSalesDocDialog kind={creating} customerId={p.id} onClose={() => setCreating(null)} onCreated={(path) => navigate(path)} />}
    </>
  )
}

function ActivityList({ title, rows }: { title: string; rows: { id: number; to: string; number: string; date: string; total: string; status: { label: string; variant: 'secondary' | 'accent' | 'success' | 'outline' | 'destructive' } }[] }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <ul className="divide-y rounded-lg border">
        {rows.map((r) => (
          <li key={r.id}>
            <Link to={r.to} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-secondary/40">
              <span className="font-mono text-xs">{r.number}</span>
              <span className="text-muted-foreground">{fmtDate(r.date)}</span>
              <Badge variant={r.status.variant} className="ml-auto">
                {r.status.label}
              </Badge>
              <span className="w-24 text-right font-medium tabular-nums">{formatMoney(r.total)}</span>
            </Link>
          </li>
        ))}
        {rows.length === 0 && <li className="px-3 py-4 text-center text-sm text-muted-foreground">Aucun</li>}
      </ul>
    </div>
  )
}

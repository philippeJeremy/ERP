import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Banknote,
  Boxes,
  Building,
  EllipsisVertical,
  LoaderCircle,
  MapPin,
  Power,
  ShoppingCart,
  Trash2,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ErrorAlert } from '@/components/ui/field'
import { api, ApiError } from '@/lib/api'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { SupplierArticlesTab } from '@/pages/catalog/SupplierArticlesTab'
import { NewOrderDialog } from '@/pages/purchasing/PurchaseOrdersPage'
import { AddressesTab } from '@/pages/partners/AddressesTab'
import { ContactsTab } from '@/pages/partners/ContactsTab'
import { InfoForm, TermsForm } from '@/pages/partners/SupplierForms'
import { describePaymentTerms, formatMoney, type Partner } from '@/pages/partners/types'

const TABS: { id: string; label: string; icon: LucideIcon }[] = [
  { id: 'informations', label: 'Informations', icon: Building },
  { id: 'adresses', label: 'Adresses', icon: MapPin },
  { id: 'contacts', label: 'Contacts', icon: UsersRound },
  { id: 'conditions', label: "Conditions d'achat et banque", icon: Banknote },
  { id: 'articles', label: 'Articles', icon: Boxes },
]

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium">{value ?? '—'}</dd>
    </div>
  )
}

export function SupplierPage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = TABS.find((t) => t.id === params.get('onglet'))?.id ?? 'informations'
  const [deleting, setDeleting] = useState(false)
  const [ordering, setOrdering] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const readOnly = !can(me?.permissions, 'partners:manage')

  const partner = useQuery({
    queryKey: ['partner', company?.id, Number(id)],
    queryFn: () => api<Partner>(`/partners/${id}`),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  })
  const toggleActive = useMutation({
    mutationFn: (p: Partner) =>
      api<Partner>(`/partners/${p.id}`, { method: 'PATCH', body: { version: p.version, is_active: !p.is_active } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['partner', company?.id, saved.id], saved)
      void queryClient.invalidateQueries({ queryKey: ['partners'] })
    },
  })

  if (partner.isPending) return <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
  if (partner.isError) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorAlert error={partner.error} />
      </div>
    )
  }
  const p = partner.data
  const counts: Record<string, number> = { adresses: p.addresses.length, contacts: p.contacts.length }

  return (
    <>
      <BackLink />
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-accent/20 text-sm font-semibold text-accent-foreground">
            {p.name.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
              {p.name}
              {!p.is_active && <Badge variant="outline">Désactivé</Badge>}
              {p.is_customer && <Badge variant="secondary">Aussi client</Badge>}
            </h1>
            <p className="text-sm text-muted-foreground">
              <span className="font-mono">{p.code}</span>
              {p.legal_form && ` · ${p.legal_form}`}
              {p.parent && ` · Groupement : ${p.parent.name}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
        {can(me?.permissions, 'purchasing:manage') && p.is_active && (
          <Button onClick={() => setOrdering(true)}>
            <ShoppingCart /> Commander
          </Button>
        )}
        {!readOnly && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Actions">
                <EllipsisVertical />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => toggleActive.mutate(p)}>
                <Power /> {p.is_active ? 'Désactiver' : 'Réactiver'}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDeleting(true)}>
                <Trash2 /> Supprimer
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        </div>
      </div>

      {/* L'essentiel en un coup d'œil, quel que soit l'onglet. */}
      <dl className="mb-6 grid grid-cols-2 gap-4 rounded-xl border bg-card p-4 shadow-xs sm:grid-cols-4">
        <Fact label="Règlement" value={describePaymentTerms(p)} />
        <Fact label="Délai de livraison" value={p.lead_time_days !== null ? `${p.lead_time_days} jour${p.lead_time_days > 1 ? 's' : ''}` : null} />
        <Fact label="Franco de port" value={p.free_shipping_amount ? formatMoney(p.free_shipping_amount, p.currency) : null} />
        <Fact label="Minimum de commande" value={p.min_order_amount ? formatMoney(p.min_order_amount, p.currency) : null} />
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
              '-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <t.icon className="size-4" />
            {t.label}
            {counts[t.id] > 0 && <span className="rounded-full bg-secondary px-1.5 text-xs">{counts[t.id]}</span>}
          </button>
        ))}
      </div>

      <div className="rounded-xl border bg-card px-6 pt-6 shadow-xs">
        {tab === 'informations' && <InfoForm partner={p} readOnly={readOnly} />}
        {tab === 'conditions' && <TermsForm partner={p} readOnly={readOnly} />}
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
        {tab === 'articles' && <SupplierArticlesTab partnerId={p.id} />}
      </div>

      {deleting && <DeleteDialog partner={p} onClose={() => setDeleting(false)} />}
      {ordering && <NewOrderDialog partnerId={p.id} onClose={() => setOrdering(false)} onCreated={(id) => navigate(`/achats/${id}`)} />}
    </>
  )
}

function BackLink() {
  return (
    <Link to="/fournisseurs" onClick={(e) => {
      // Revenir à la liste telle qu'on l'a laissée (recherche, page) quand on vient d'elle.
      if (window.history.state?.idx > 0) {
        e.preventDefault()
        window.history.back()
      }
    }} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Fournisseurs
    </Link>
  )
}

function DeleteDialog({ partner, onClose }: { partner: Partner; onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const remove = useMutation({
    mutationFn: () => api<void>(`/partners/${partner.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['partners'] })
      navigate('/fournisseurs', { replace: true })
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Supprimer « {partner.name} » ?</DialogTitle>
          <DialogDescription>
            Action définitive : la fiche, ses adresses et ses contacts sont supprimés. Réservée aux fiches créées par
            erreur : un fournisseur qui a des articles ou des commandes ne peut pas être supprimé, il faut le désactiver.
          </DialogDescription>
        </DialogHeader>
        <ErrorAlert error={remove.error} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {remove.isPending && <LoaderCircle className="animate-spin" />}
            Supprimer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

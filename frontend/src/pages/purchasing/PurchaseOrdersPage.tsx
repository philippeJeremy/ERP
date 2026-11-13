import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { LoaderCircle, Plus, Search, Settings, ShoppingCart } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import type { PartnerPage } from '@/pages/partners/types'
import { formatDate, money, ORDER_STATUSES, orderTitle, type Order, type OrderListItem, type Site } from '@/pages/purchasing/types'

const PAGE_SIZE = 25
const GROUPS = [
  { id: 'a_traiter', label: 'À traiter' },
  { id: 'en_cours', label: 'En cours' },
  { id: 'terminees', label: 'Terminées' },
  { id: '', label: 'Toutes' },
] as const

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, OrderListItem>()
const columns = helper.columns([
  helper.accessor('number', {
    header: 'Commande',
    cell: ({ row }) => (
      <span className={cn('font-mono text-xs', !row.original.number && 'text-muted-foreground italic')}>{orderTitle(row.original)}</span>
    ),
  }),
  helper.accessor('partner_name', { header: 'Fournisseur', cell: (i) => <span className="font-medium">{i.getValue()}</span> }),
  helper.accessor('site_name', { header: 'Livraison', cell: (i) => i.getValue() }),
  helper.accessor('order_date', { header: 'Date', cell: (i) => formatDate(i.getValue()) }),
  helper.accessor('expected_date', { header: 'Prévue le', cell: (i) => formatDate(i.getValue()) }),
  helper.accessor('total_ht', { header: 'Montant HT', cell: (i) => <span className="tabular-nums">{money(i.getValue())}</span> }),
  helper.accessor('status', {
    header: 'Statut',
    cell: ({ row }) => {
      const s = ORDER_STATUSES[row.original.status]
      return (
        <div className="space-y-1">
          <Badge variant={s.variant}>{s.label}</Badge>
          {['envoyee', 'confirmee', 'partielle', 'recue'].includes(row.original.status) && (
            <div className="h-1 w-20 overflow-hidden rounded bg-secondary" title={`${Math.round(row.original.received_ratio * 100)} % reçu`}>
              <div className="h-full bg-emerald-600" style={{ width: `${row.original.received_ratio * 100}%` }} />
            </div>
          )}
        </div>
      )
    },
  }),
])
const CELL: Record<string, string> = {
  site_name: 'hidden lg:table-cell',
  order_date: 'hidden md:table-cell',
  expected_date: 'hidden xl:table-cell',
  total_ht: 'text-right',
}
const NO_ROWS: OrderListItem[] = []

export function PurchaseOrdersPage() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const [settings, setSettings] = useState(false)
  const vue = params.get('vue') ?? 'a_traiter'
  const group = GROUPS.find((g) => g.id === (vue === 'toutes' ? '' : vue))?.id ?? 'a_traiter'
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (group) query.set('group', group)
  if (q) query.set('q', q)
  const allowed = can(me?.permissions, 'purchasing:read')
  const list = useQuery({
    queryKey: ['purchase-orders', company?.id, query.toString()],
    queryFn: () => api<{ items: OrderListItem[]; total: number }>(`/purchasing/orders?${query}`),
    placeholderData: keepPreviousData,
    enabled: allowed,
  })
  const table = useTable({ features, columns, data: list.data?.items ?? NO_ROWS })

  if (!allowed) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir les achats.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <PageHeader
        title="Commandes fournisseur"
        description="De la commande à la réception : validation, bon de commande PDF, accusé du fournisseur, livraisons."
        actions={
          <div className="flex gap-2">
            {can(me?.permissions, 'purchasing:approve') && (
              <Button variant="outline" onClick={() => setSettings(true)}>
                <Settings /> Réglages
              </Button>
            )}
            {can(me?.permissions, 'purchasing:manage') && (
              <Button onClick={() => setCreating(true)}>
                <Plus /> Nouvelle commande
              </Button>
            )}
          </div>
        }
      />
      <div role="tablist" className="mb-4 flex gap-1 border-b">
        {GROUPS.map((g) => (
          <button
            key={g.id}
            role="tab"
            type="button"
            aria-selected={group === g.id}
            onClick={() => update({ vue: g.id === 'a_traiter' ? null : g.id || 'toutes', page: null })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              group === g.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {g.label}
          </button>
        ))}
      </div>
      <div className="mb-4 flex items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher une commande" placeholder="N° de commande, fournisseur, n° d'accusé…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} className={cn('px-4 py-2.5 font-medium', CELL[h.id])}>
                    <table.FlexRender header={h} />
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y">
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/achats/${row.original.id}`)}>
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className={cn('px-4 py-3', CELL[cell.column.id])}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <ShoppingCart className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucune commande {group === 'a_traiter' ? 'à traiter' : ''}</p>
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['commande', 'commandes']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <NewOrderDialog onClose={() => setCreating(false)} onCreated={(id) => navigate(`/achats/${id}`)} />}
      {settings && <SettingsDialog onClose={() => setSettings(false)} />}
    </>
  )
}

export function NewOrderDialog({ onClose, onCreated, partnerId }: { onClose: () => void; onCreated: (id: number) => void; partnerId?: number }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [partner, setPartner] = useState(partnerId ? String(partnerId) : '')
  const [site, setSite] = useState('')
  const [expected, setExpected] = useState('')
  const suppliers = useQuery({
    queryKey: ['partners', company?.id, 'supplier-options'],
    queryFn: () => api<PartnerPage>('/partners?role=supplier&active=true&limit=200&sort=name'),
  })
  const sites = useQuery({ queryKey: ['sites', company?.id, 'active'], queryFn: () => api<Site[]>('/org/sites?active=true') })
  const siteId = site || (sites.data?.[0] ? String(sites.data[0].id) : '')
  const create = useMutation({
    mutationFn: () =>
      api<Order>('/purchasing/orders', { method: 'POST', body: { partner_id: Number(partner), site_id: siteId ? Number(siteId) : null, expected_date: expected || null } }),
    onSuccess: (o) => {
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] })
      onCreated(o.id)
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouvelle commande fournisseur</DialogTitle>
          <DialogDescription>Un brouillon est créé : vous ajoutez ensuite les articles. Le numéro est attribué à la validation.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field id="po_partner" label="Fournisseur">
            <NativeSelect id="po_partner" value={partner} onChange={(e) => setPartner(e.target.value)}>
              <option value="">— Choisir —</option>
              {suppliers.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.code})
                </option>
              ))}
            </NativeSelect>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="po_site" label="Livrer au dépôt">
              <NativeSelect id="po_site" value={siteId} onChange={(e) => setSite(e.target.value)} disabled={!sites.data?.length}>
                {!sites.data?.length && <option value="">Aucun dépôt</option>}
                {sites.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} — {s.city}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="po_expected" label="Livraison souhaitée le">
              <Input id="po_expected" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
            </Field>
          </div>
          {sites.data?.length === 0 && (
            <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">Déclarez d'abord un dépôt (menu Administration → Dépôts) : c'est l'adresse de livraison.</p>
          )}
        </div>
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!partner || !siteId || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <LoaderCircle className="animate-spin" />}
            Créer le brouillon
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const current = useQuery({
    queryKey: ['purchasing-settings', company?.id],
    queryFn: () => api<{ approval_threshold: string | null; order_footer: string | null }>('/purchasing/settings'),
  })
  const [threshold, setThreshold] = useState<string | null>(null)
  const [footer, setFooter] = useState<string | null>(null)
  const t = threshold ?? (current.data?.approval_threshold ? String(Number(current.data.approval_threshold)) : '')
  const f = footer ?? current.data?.order_footer ?? ''
  const invalid = t !== '' && !/^\d{1,12}([.,]\d{1,2})?$/.test(t)
  const save = useMutation({
    mutationFn: () => api('/purchasing/settings', { method: 'PUT', body: { approval_threshold: t ? t.replace(',', '.') : null, order_footer: f || null } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['purchasing-settings'] })
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Réglages des achats — {company?.name}</DialogTitle>
          <DialogDescription>Propres à la société courante.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field id="set_threshold" label="Seuil de validation (€ HT)" error={invalid ? 'Montant invalide' : undefined} hint="Au-delà, une commande doit être approuvée par quelqu'un qui a le droit « valider les achats ». Vide : pas de validation.">
            <Input id="set_threshold" inputMode="decimal" value={t} onChange={(e) => setThreshold(e.target.value)} />
          </Field>
          <Field id="set_footer" label="Mentions en bas des bons de commande" hint="Conditions générales d'achat, horaires de réception…">
            <Textarea id="set_footer" rows={3} value={f} onChange={(e) => setFooter(e.target.value)} />
          </Field>
        </div>
        <ErrorAlert error={save.error ?? current.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={invalid || save.isPending || current.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

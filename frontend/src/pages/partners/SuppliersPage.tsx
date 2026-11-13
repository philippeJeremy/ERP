import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type PaginationState,
  type SortingState,
  type Updater,
} from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, LoaderCircle, Plus, Search, Truck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { cn } from '@/lib/utils'
import { CreateSupplierDialog } from '@/pages/partners/CreateSupplierDialog'
import type { PartnerListItem, PartnerPage } from '@/pages/partners/types'

const PAGE_SIZE = 25
const SORTABLE = ['code', 'name'] as const
const STATUSES = [
  { id: 'actifs', label: 'Actifs' },
  { id: 'inactifs', label: 'Désactivés' },
  { id: 'tous', label: 'Tous' },
] as const

// Hors du composant : TanStack Table exige des « features » et colonnes stables.
const features = tableFeatures({ rowSortingFeature, rowPaginationFeature })
const helper = createColumnHelper<typeof features, PartnerListItem>()
const columns = helper.columns([
  helper.accessor('code', {
    header: 'Code',
    cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
  }),
  helper.accessor('name', {
    header: 'Fournisseur',
    cell: ({ row }) => (
      <div className="min-w-0">
        <p className="truncate font-medium">{row.original.name}</p>
        {row.original.siret && <p className="font-mono text-xs text-muted-foreground">{row.original.siret}</p>}
      </div>
    ),
  }),
  helper.accessor('city', { header: 'Ville', enableSorting: false, cell: (info) => info.getValue() ?? '—' }),
  helper.accessor('contact_name', {
    header: 'Interlocuteur',
    enableSorting: false,
    cell: (info) => info.getValue() ?? <span className="text-muted-foreground">—</span>,
  }),
  helper.accessor('phone', {
    header: 'Coordonnées',
    enableSorting: false,
    cell: ({ row }) => (
      <div className="text-xs leading-5 text-muted-foreground">
        {row.original.phone && <p>{row.original.phone}</p>}
        {row.original.email && <p className="truncate">{row.original.email}</p>}
        {!row.original.phone && !row.original.email && '—'}
      </div>
    ),
  }),
  helper.accessor('is_active', {
    header: 'Statut',
    enableSorting: false,
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {row.original.is_active ? <Badge variant="success">Actif</Badge> : <Badge variant="outline">Désactivé</Badge>}
        {row.original.is_customer && <Badge variant="secondary">Aussi client</Badge>}
      </div>
    ),
  }),
])
// Colonnes masquées sur petit écran (le code et le nom restent toujours visibles).
const HIDDEN_ON_MOBILE: Record<string, string> = {
  city: 'hidden md:table-cell',
  contact_name: 'hidden lg:table-cell',
  phone: 'hidden xl:table-cell',
}
const NO_ROWS: PartnerListItem[] = []

export function SuppliersPage() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  // Recherche, filtre, tri et page sont dans l'URL : le bouton « retour » depuis une
  // fiche retrouve exactement la même liste, et le lien se partage.
  const [params, setParams] = useSearchParams()
  const status = STATUSES.find((s) => s.id === params.get('statut'))?.id ?? 'actifs'
  const sortParam = params.get('tri') ?? 'name'
  const sorting: SortingState = [
    { id: SORTABLE.includes(sortParam.replace(/^-/, '') as never) ? sortParam.replace(/^-/, '') : 'name', desc: sortParam.startsWith('-') },
  ]
  const pagination: PaginationState = { pageIndex: Math.max(0, Number(params.get('page') ?? 1) - 1), pageSize: PAGE_SIZE }
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())

  const update = (changes: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === '') next.delete(k)
          else next.set(k, v)
        }
        return next
      },
      { replace: true },
    )

  useEffect(() => {
    // Nouvelle recherche : retour à la première page.
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const query = new URLSearchParams({
    role: 'supplier',
    sort: sorting[0].id,
    order: sorting[0].desc ? 'desc' : 'asc',
    limit: String(PAGE_SIZE),
    offset: String(pagination.pageIndex * PAGE_SIZE),
  })
  if (q) query.set('q', q)
  if (status !== 'tous') query.set('active', String(status === 'actifs'))

  const allowed = can(me?.permissions, 'partners:read')
  const list = useQuery({
    queryKey: ['partners', company?.id, query.toString()],
    queryFn: () => api<PartnerPage>(`/partners?${query}`),
    placeholderData: keepPreviousData, // garde la page affichée pendant le chargement de la suivante
    enabled: allowed,
  })

  const resolve = <T,>(updater: Updater<T>, current: T): T =>
    typeof updater === 'function' ? (updater as (old: T) => T)(current) : updater

  const table = useTable({
    features,
    columns,
    data: list.data?.items ?? NO_ROWS,
    rowCount: list.data?.total ?? 0,
    // Tri et pagination faits par l'API (PostgreSQL), pas dans le navigateur.
    manualSorting: true,
    manualPagination: true,
    enableSortingRemoval: false,
    state: { sorting, pagination },
    onSortingChange: (updater) => {
      const [s] = resolve(updater, sorting)
      if (s) update({ tri: s.id === 'name' && !s.desc ? null : `${s.desc ? '-' : ''}${s.id}`, page: null })
    },
    onPaginationChange: (updater) => {
      const p = resolve(updater, pagination)
      update({ page: p.pageIndex === 0 ? null : String(p.pageIndex + 1) })
    },
  })

  if (!allowed) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir les fournisseurs de cette société.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const total = list.data?.total ?? 0
  const first = total === 0 ? 0 : pagination.pageIndex * PAGE_SIZE + 1
  const last = Math.min(total, (pagination.pageIndex + 1) * PAGE_SIZE)

  return (
    <>
      <PageHeader
        title="Fournisseurs"
        description={`Le référentiel fournisseurs de ${company?.name} : coordonnées, contacts, conditions d'achat.`}
        actions={
          can(me?.permissions, 'partners:manage') && (
            <Button onClick={() => setCreating(true)}>
              <Plus /> Nouveau fournisseur
            </Button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Rechercher un fournisseur"
            placeholder="Code, nom, SIRET, e-mail, contact…"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div role="radiogroup" aria-label="Statut" className="flex rounded-md border bg-card p-0.5 shadow-xs">
          {STATUSES.map((s) => (
            <button
              key={s.id}
              type="button"
              role="radio"
              aria-checked={status === s.id}
              onClick={() => update({ statut: s.id === 'actifs' ? null : s.id, page: null })}
              className={cn(
                'rounded px-3 py-1 text-sm transition-colors',
                status === s.id ? 'bg-secondary font-medium text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>

      <ErrorAlert error={list.error} />

      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sortable = header.column.getCanSort()
                  const sorted = header.column.getIsSorted()
                  const Icon = sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ArrowUpDown
                  return (
                    <th
                      key={header.id}
                      className={cn('px-4 py-2.5 font-medium', HIDDEN_ON_MOBILE[header.id])}
                      aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    >
                      {sortable ? (
                        <button
                          type="button"
                          className="-mx-1 inline-flex items-center gap-1 rounded px-1 hover:text-foreground"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          <table.FlexRender header={header} />
                          <Icon className={cn('size-3.5', !sorted && 'opacity-40')} />
                        </button>
                      ) : (
                        <table.FlexRender header={header} />
                      )}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y">
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn('cursor-pointer transition-colors hover:bg-secondary/40', !row.original.is_active && 'opacity-60')}
                onClick={() => navigate(`/fournisseurs/${row.original.id}`)}
              >
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className={cn('px-4 py-3', HIDDEN_ON_MOBILE[cell.column.id])}>
                    {cell.column.id === 'name' ? (
                      // Vrai lien : accessible au clavier, et « ouvrir dans un nouvel onglet » fonctionne.
                      <a href={`/fournisseurs/${row.original.id}`} onClick={(e) => e.preventDefault()} className="block">
                        <table.FlexRender cell={cell} />
                      </a>
                    ) : (
                      <table.FlexRender cell={cell} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {list.isSuccess && total === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
            <Truck className="size-8 text-muted-foreground/60" />
            <p className="font-medium">{q ? 'Aucun fournisseur ne correspond à la recherche' : 'Aucun fournisseur pour le moment'}</p>
            {!q && can(me?.permissions, 'partners:manage') && (
              <Button variant="outline" size="sm" onClick={() => setCreating(true)}>
                <Plus /> Créer le premier
              </Button>
            )}
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>

      {total > 0 && (
        <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {first}–{last} sur {total} fournisseur{total > 1 ? 's' : ''}
          </span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" aria-label="Page précédente" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
              <ChevronLeft />
            </Button>
            <span className="px-2">
              Page {pagination.pageIndex + 1} / {table.getPageCount()}
            </span>
            <Button variant="outline" size="icon" aria-label="Page suivante" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}

      {creating && <CreateSupplierDialog onClose={() => setCreating(false)} onCreated={(id) => navigate(`/fournisseurs/${id}`)} />}
    </>
  )
}

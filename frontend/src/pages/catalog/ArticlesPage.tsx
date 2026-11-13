import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type SortingState,
  type Updater,
} from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, FileUp, LoaderCircle, Package, Plus, Search, Snowflake, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { ArticleDialog } from '@/pages/catalog/ArticleDialog'
import { EuLabel } from '@/pages/catalog/EuLabel'
import { formatPrice, KINDS, SEASONS, VEHICLE_TYPES, type ArticleListItem, type Page, type Season } from '@/pages/catalog/types'

const PAGE_SIZE = 25
const TABS = [
  { id: '', label: 'Tous' },
  { id: 'pneu', label: 'Pneus' },
  { id: 'piece', label: 'Pièces' },
  { id: 'accessoire', label: 'Accessoires' },
] as const
const SORTABLE = ['code', 'designation', 'brand', 'size', 'best_price']

export function SeasonBadge({ season }: { season: Season | null }) {
  if (!season) return <span className="text-muted-foreground">—</span>
  const Icon = season === 'hiver' ? Snowflake : season === 'ete' ? Sun : null
  return (
    <Badge variant="secondary">
      {Icon && <Icon />} {SEASONS[season]}
    </Badge>
  )
}

const features = tableFeatures({ rowSortingFeature })
const helper = createColumnHelper<typeof features, ArticleListItem>()
const columns = helper.columns([
  helper.accessor('code', { header: 'Code', cell: (i) => <span className="font-mono text-xs">{i.getValue()}</span> }),
  helper.accessor('designation', {
    header: 'Désignation',
    cell: ({ row }) => (
      <div className="min-w-0">
        <p className="font-medium">{row.original.designation}</p>
        <p className="text-xs text-muted-foreground">
          {[row.original.kind !== 'pneu' && KINDS[row.original.kind], row.original.ean].filter(Boolean).join(' · ') || ' '}
        </p>
      </div>
    ),
  }),
  helper.accessor('brand', { header: 'Marque', cell: (i) => i.getValue() ?? '—' }),
  helper.accessor('size', {
    id: 'size',
    header: 'Dimension',
    cell: ({ row }) =>
      row.original.size ? (
        <div>
          <p className="font-mono text-xs whitespace-nowrap">{row.original.size}</p>
          {row.original.vehicle_type && <p className="text-xs text-muted-foreground">{VEHICLE_TYPES[row.original.vehicle_type]}</p>}
        </div>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  }),
  helper.accessor('season', { header: 'Saison', enableSorting: false, cell: (i) => <SeasonBadge season={i.getValue()} /> }),
  helper.accessor('fuel_class', {
    header: 'Étiquette UE',
    enableSorting: false,
    cell: ({ row }) => <EuLabel fuel={row.original.fuel_class} wet={row.original.wet_class} noise={row.original.noise_db} />,
  }),
  helper.accessor('best_price', {
    header: 'Meilleur prix',
    cell: ({ row }) => (
      <div className="text-right">
        <p className="font-medium tabular-nums">{formatPrice(row.original.best_price)}</p>
        <p className="text-xs text-muted-foreground">
          {row.original.supplier_count === 0
            ? 'aucun fournisseur'
            : `${row.original.supplier_count} fournisseur${row.original.supplier_count > 1 ? 's' : ''}`}
        </p>
      </div>
    ),
  }),
])
const CELL_CLASS: Record<string, string> = {
  brand: 'hidden lg:table-cell',
  size: 'hidden md:table-cell',
  season: 'hidden xl:table-cell',
  fuel_class: 'hidden xl:table-cell',
  best_price: 'text-right',
}
const NO_ROWS: ArticleListItem[] = []

export function ArticlesPage() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const [params, update] = useUrlState()
  const kind = TABS.find((t) => t.id === params.get('type'))?.id ?? ''
  const season = params.get('saison') ?? ''
  const vehicle = params.get('vehicule') ?? ''
  const status = params.get('statut') ?? ''
  const sortParam = params.get('tri') ?? 'designation'
  const sortId = SORTABLE.includes(sortParam.replace(/^-/, '')) ? sortParam.replace(/^-/, '') : 'designation'
  const sorting: SortingState = [{ id: sortId, desc: sortParam.startsWith('-') }]
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())

  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const query = new URLSearchParams({
    sort: sortId,
    order: sorting[0].desc ? 'desc' : 'asc',
    limit: String(PAGE_SIZE),
    offset: String(page * PAGE_SIZE),
  })
  if (kind) query.set('kind', kind)
  if (q) query.set('q', q)
  if (season) query.set('season', season)
  if (vehicle) query.set('vehicle_type', vehicle)
  query.set('active', status === 'inactifs' ? 'false' : 'true')

  const allowed = can(me?.permissions, 'catalog:read')
  const list = useQuery({
    queryKey: ['articles', company?.id, query.toString()],
    queryFn: () => api<Page<ArticleListItem>>(`/catalog/articles?${query}`),
    placeholderData: keepPreviousData,
    enabled: allowed,
  })
  const table = useTable({
    features,
    columns,
    data: list.data?.items ?? NO_ROWS,
    manualSorting: true,
    enableSortingRemoval: false,
    state: { sorting },
    onSortingChange: (updater: Updater<SortingState>) => {
      const [s] = typeof updater === 'function' ? updater(sorting) : updater
      if (s) update({ tri: s.id === 'designation' && !s.desc ? null : `${s.desc ? '-' : ''}${s.id}`, page: null })
    },
  })

  if (!allowed) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir le catalogue d'articles.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  const total = list.data?.total ?? 0

  return (
    <>
      <PageHeader
        title="Articles"
        description="Le catalogue commun au groupe : pneus, pièces et accessoires. Les prix d'achat sont ceux de votre société."
        actions={
          <div className="flex gap-2">
            {can(me?.permissions, 'catalog:import') && (
              <Button variant="outline" asChild>
                <Link to="/articles/imports">
                  <FileUp /> Imports tarifs
                </Link>
              </Button>
            )}
            {can(me?.permissions, 'catalog:manage') && (
              <Button onClick={() => setCreating(true)}>
                <Plus /> Nouvel article
              </Button>
            )}
          </div>
        }
      />

      <div role="tablist" className="mb-4 flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={kind === t.id}
            onClick={() => update({ type: t.id || null, page: null, saison: t.id === 'pneu' || !t.id ? season : null, vehicule: t.id === 'pneu' || !t.id ? vehicle : null })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              kind === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Rechercher un article"
            placeholder="Désignation, EAN, référence, marque, dimension (205/55R16)…"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {kind !== 'piece' && kind !== 'accessoire' && (
          <>
            <NativeSelect aria-label="Saison" className="w-auto" value={season} onChange={(e) => update({ saison: e.target.value, page: null })}>
              <option value="">Toutes saisons</option>
              {Object.entries(SEASONS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect aria-label="Type de véhicule" className="w-auto" value={vehicle} onChange={(e) => update({ vehicule: e.target.value, page: null })}>
              <option value="">Tous véhicules</option>
              {Object.entries(VEHICLE_TYPES).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </NativeSelect>
          </>
        )}
        <NativeSelect aria-label="Statut" className="w-auto" value={status} onChange={(e) => update({ statut: e.target.value, page: null })}>
          <option value="">Actifs</option>
          <option value="inactifs">Désactivés</option>
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>

      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted()
                  const Icon = sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ArrowUpDown
                  return (
                    <th
                      key={header.id}
                      className={cn('px-4 py-2.5 font-medium', CELL_CLASS[header.id])}
                      aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    >
                      {header.column.getCanSort() ? (
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
              <tr key={row.id} className="cursor-pointer transition-colors hover:bg-secondary/40" onClick={() => navigate(`/articles/${row.original.id}`)}>
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className={cn('px-4 py-3', CELL_CLASS[cell.column.id])}>
                    {cell.column.id === 'designation' ? (
                      <a href={`/articles/${row.original.id}`} onClick={(e) => e.preventDefault()} className="block">
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
            <Package className="size-8 text-muted-foreground/60" />
            <p className="font-medium">{q ? 'Aucun article ne correspond à la recherche' : 'Aucun article pour le moment'}</p>
            {!q && can(me?.permissions, 'catalog:import') && (
              <p className="max-w-sm text-sm text-muted-foreground">
                Le plus simple pour démarrer : <Link className="text-primary underline" to="/articles/imports/nouveau">importer le tarif d'un fournisseur</Link>.
              </p>
            )}
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={total} noun={['article', 'articles']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />

      {creating && <ArticleDialog article={null} onClose={() => setCreating(false)} onSaved={(a) => navigate(`/articles/${a.id}`)} />}
    </>
  )
}

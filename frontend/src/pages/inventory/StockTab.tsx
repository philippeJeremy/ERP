import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { Boxes, LoaderCircle, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { AdjustDialog } from '@/pages/inventory/AdjustDialog'
import { useSites } from '@/pages/inventory/hooks'
import { DotBadge } from '@/pages/inventory/parts'
import { fmtCost, fmtMoney, fmtQty, type StockPage, type StockRow } from '@/pages/inventory/types'

const PAGE_SIZE = 25
const SORTS = {
  value: 'Valeur',
  quantity: 'Quantité',
  dot: 'DOT le plus ancien',
} as const

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, StockRow>()
const columns = helper.columns([
  helper.accessor((r) => r.article.designation, {
    id: 'article',
    header: 'Article',
    cell: ({ row }) => (
      <>
        <Link to={`/articles/${row.original.article.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
          {row.original.article.designation}
        </Link>
        <span className="block font-mono text-xs text-muted-foreground">
          {row.original.article.code}
          {row.original.article.ean && ` · ${row.original.article.ean}`}
        </span>
      </>
    ),
  }),
  helper.accessor('oldest_dot', { header: 'Plus vieux DOT', cell: (i) => <DotBadge dot={i.getValue()} /> }),
  helper.accessor('quantity', { header: 'Quantité', cell: (i) => <span className="font-medium tabular-nums">{fmtQty(i.getValue())}</span> }),
  helper.accessor('reserved', {
    header: 'Réservé',
    cell: (i) => (Number(i.getValue()) ? <span className="tabular-nums text-muted-foreground">{fmtQty(i.getValue())}</span> : ''),
  }),
  helper.accessor('available', {
    header: 'Disponible',
    cell: (i) => <span className={cn('font-medium tabular-nums', Number(i.getValue()) < 0 && 'text-destructive')}>{fmtQty(i.getValue())}</span>,
  }),
  helper.accessor('average_cost', { header: 'CMP', cell: (i) => <span className="tabular-nums text-muted-foreground">{fmtCost(i.getValue())}</span> }),
  helper.accessor('value', { header: 'Valeur', cell: (i) => <span className="font-medium tabular-nums">{fmtMoney(i.getValue())}</span> }),
])
const CELL: Record<string, string> = {
  oldest_dot: 'hidden sm:table-cell',
  quantity: 'text-right',
  reserved: 'hidden lg:table-cell text-right',
  available: 'text-right',
  average_cost: 'hidden md:table-cell text-right',
  value: 'text-right',
}
const NO_ROWS: StockRow[] = []

export function StockTab() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [adjusting, setAdjusting] = useState(false)
  const sites = useSites()
  const site = params.get('depot') ?? ''
  const kind = params.get('type') ?? ''
  const sort = (params.get('tri') ?? 'value') as keyof typeof SORTS
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE), sort, order: sort === 'dot' ? 'asc' : 'desc' })
  if (site) query.set('site_id', site)
  if (kind) query.set('kind', kind)
  if (q) query.set('q', q)
  const stock = useQuery({
    queryKey: ['stock', company?.id, query.toString()],
    queryFn: () => api<StockPage>(`/inventory/stock?${query}`),
    placeholderData: keepPreviousData,
  })
  const table = useTable({ features, columns, data: stock.data?.items ?? NO_ROWS })
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        {[
          ['Articles en stock', stock.data ? fmtQty(stock.data.total) : '…'],
          ['Quantité totale', stock.data ? fmtQty(stock.data.total_quantity) : '…'],
          ['Valeur du stock (CMP)', stock.data ? fmtMoney(stock.data.total_value) : '…'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border bg-card p-4 shadow-xs">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
          </div>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher dans le stock" placeholder="Désignation, dimension, EAN, code…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Dépôt" className="w-44" value={site} onChange={(e) => update({ depot: e.target.value, page: null })}>
          <option value="">Tous les dépôts</option>
          {sites.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Type d'article" className="w-36" value={kind} onChange={(e) => update({ type: e.target.value, page: null })}>
          <option value="">Tous types</option>
          <option value="pneu">Pneus</option>
          <option value="piece">Pièces</option>
          <option value="accessoire">Accessoires</option>
        </NativeSelect>
        <NativeSelect aria-label="Trier par" className="w-48" value={sort} onChange={(e) => update({ tri: e.target.value === 'value' ? null : e.target.value, page: null })}>
          {Object.entries(SORTS).map(([k, v]) => (
            <option key={k} value={k}>
              Trier : {v}
            </option>
          ))}
        </NativeSelect>
        {stock.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {can(me?.permissions, 'inventory:manage') && (
          <Button variant="outline" className="ml-auto" onClick={() => setAdjusting(true)}>
            <SlidersHorizontal /> Ajuster
          </Button>
        )}
      </div>
      <ErrorAlert error={stock.error} />
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
              <tr key={row.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/articles/${row.original.article.id}`)}>
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className={cn('px-4 py-3', CELL[cell.column.id])}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {stock.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <Boxes className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun article en stock</p>
            <p className="text-sm text-muted-foreground">Le stock se remplit à la réception des commandes fournisseur.</p>
          </div>
        )}
        {stock.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={stock.data?.total ?? 0} noun={['article', 'articles']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {adjusting && <AdjustDialog siteId={site ? Number(site) : undefined} onClose={() => setAdjusting(false)} />}
    </>
  )
}

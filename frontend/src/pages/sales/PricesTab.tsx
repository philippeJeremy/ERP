import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, LoaderCircle, Search, Tags } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { fmtCost, fmtMoney } from '@/pages/inventory/types'
import { fmtPct, type PriceRow } from '@/pages/sales/types'

const PAGE_SIZE = 25
const NUM = /^\d{1,10}([.,]\d{1,4})?$/
const show = (v: string | null) => (v === null ? '' : String(Number(v)).replace('.', ','))

/** Tarif de vente : sans recherche, les articles tarifés ; avec recherche, tout le catalogue. */
export function PricesTab() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const missing = params.get('sans_prix') === '1'
  const kind = params.get('type') ?? ''
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (q) query.set('q', q)
  if (kind) query.set('kind', kind)
  if (missing) query.set('missing', 'true')
  const list = useQuery({
    queryKey: ['prices', company?.id, query.toString()],
    queryFn: () => api<{ items: PriceRow[]; total: number }>(`/sales/prices?${query}`),
    placeholderData: keepPreviousData,
  })
  const editable = can(me?.permissions, 'sales:prices')
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher un article" placeholder="Désignation, dimension (2055516), EAN…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Type d'article" className="w-36" value={kind} onChange={(e) => update({ type: e.target.value, page: null })}>
          <option value="">Tous types</option>
          <option value="pneu">Pneus</option>
          <option value="piece">Pièces</option>
          <option value="accessoire">Accessoires</option>
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={missing} onChange={(e) => update({ sans_prix: e.target.checked ? '1' : null, page: null })} />
          Sans prix seulement
        </label>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>
      <p className="mb-3 text-sm text-muted-foreground">
        Prix public HT, avant la remise de chaque client. L'éco-contribution (pneus) s'ajoute au prix, sans remise. La marge est calculée au coût moyen du stock.
      </p>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Article</th>
              <th className="hidden px-4 py-2.5 text-right font-medium md:table-cell">Coût moyen</th>
              <th className="w-36 px-4 py-2.5 font-medium">Prix de vente HT</th>
              <th className="w-32 px-4 py-2.5 font-medium">Éco-contr.</th>
              <th className="px-4 py-2.5 text-right font-medium">Marge</th>
              {editable && <th className="w-24" />}
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((row) => (
              <PriceLine key={row.article.id} row={row} editable={editable} />
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <Tags className="size-8 text-muted-foreground/60" />
            <p className="font-medium">{q || missing ? 'Aucun article' : 'Aucun article tarifé'}</p>
            {!q && !missing && <p className="text-sm text-muted-foreground">Recherchez un article pour lui donner un prix de vente.</p>}
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['article', 'articles']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
    </>
  )
}

function PriceLine({ row, editable }: { row: PriceRow; editable: boolean }) {
  const queryClient = useQueryClient()
  const [price, setPrice] = useState(show(row.sale_price))
  const [eco, setEco] = useState(show(row.eco_fee))
  const dirty = price !== show(row.sale_price) || eco !== show(row.eco_fee)
  const valid = NUM.test(price.trim()) && (eco.trim() === '' || NUM.test(eco.trim()))
  const save = useMutation({
    mutationFn: () => api<PriceRow>(`/sales/prices/${row.article.id}`, { method: 'PUT', body: { sale_price: price.trim().replace(',', '.'), eco_fee: (eco.trim() || '0').replace(',', '.') } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prices'] }),
  })
  const margin = row.margin_pct !== null ? Number(row.margin_pct) : null
  return (
    <tr>
      <td className="px-4 py-2.5">
        <Link to={`/articles/${row.article.id}`} className="font-medium hover:underline">
          {row.article.designation}
        </Link>
        <span className="block font-mono text-xs text-muted-foreground">{row.article.code}</span>
      </td>
      <td className="hidden px-4 py-2.5 text-right text-muted-foreground tabular-nums md:table-cell">{Number(row.average_cost) ? fmtCost(row.average_cost) : '—'}</td>
      <td className="px-4 py-1.5">
        {editable ? (
          <Input aria-label={`Prix ${row.article.code}`} className={cn('h-8 text-right', price && !NUM.test(price.trim()) && 'border-destructive')} inputMode="decimal" placeholder="—" value={price} onChange={(e) => setPrice(e.target.value)} />
        ) : (
          <span className="tabular-nums">{row.sale_price ? fmtMoney(row.sale_price) : '—'}</span>
        )}
      </td>
      <td className="px-4 py-1.5">
        {editable ? (
          <Input aria-label={`Éco ${row.article.code}`} className="h-8 text-right" inputMode="decimal" value={eco} onChange={(e) => setEco(e.target.value)} />
        ) : (
          <span className="tabular-nums">{Number(row.eco_fee) ? fmtMoney(row.eco_fee) : ''}</span>
        )}
      </td>
      <td className="px-4 py-2.5 text-right">{margin !== null && <Badge variant={margin < 0 ? 'destructive' : margin < 15 ? 'accent' : 'secondary'}>{fmtPct(margin)}</Badge>}</td>
      {editable && (
        <td className="px-2 py-1.5 text-right">
          {save.isSuccess && !dirty ? (
            <Check className="ml-auto size-4 text-emerald-700" />
          ) : (
            <Button size="sm" variant="outline" disabled={!dirty || !valid || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? <LoaderCircle className="animate-spin" /> : 'Enregistrer'}
            </Button>
          )}
          {save.error && <span className="block text-xs text-destructive">{(save.error as Error).message}</span>}
        </td>
      )}
    </tr>
  )
}

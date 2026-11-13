import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { History, LoaderCircle, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { useSites } from '@/pages/inventory/hooks'
import { MovesTable } from '@/pages/inventory/parts'
import { MOVE_KINDS, type Move } from '@/pages/inventory/types'

const PAGE_SIZE = 50

/** Le journal des mouvements : jamais modifié, une erreur se corrige par un nouveau mouvement. */
export function MovesTab() {
  const { company } = useAuth()
  const [params, update] = useUrlState()
  const sites = useSites()
  const article = params.get('article') ?? ''
  const site = params.get('depot') ?? ''
  const kind = params.get('type') ?? ''
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (article) query.set('article_id', article)
  if (site) query.set('site_id', site)
  if (kind) query.set('kind', kind)
  if (q) query.set('q', q)
  const moves = useQuery({
    queryKey: ['moves', company?.id, query.toString()],
    queryFn: () => api<{ items: Move[]; total: number }>(`/inventory/moves?${query}`),
    placeholderData: keepPreviousData,
  })
  const articleName = article && moves.data?.items[0]?.article.designation
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {article ? (
          <Badge variant="secondary" className="h-9 gap-2 px-3 text-sm">
            {articleName || `Article ${article}`}
            <button type="button" aria-label="Retirer le filtre article" onClick={() => update({ article: null, page: null })}>
              <X className="size-3.5" />
            </button>
          </Badge>
        ) : (
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" aria-label="Rechercher un mouvement" placeholder="Article : désignation, dimension, EAN…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        )}
        <NativeSelect aria-label="Dépôt" className="w-44" value={site} onChange={(e) => update({ depot: e.target.value, page: null })}>
          <option value="">Tous les dépôts</option>
          {sites.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Type de mouvement" className="w-40" value={kind} onChange={(e) => update({ type: e.target.value, page: null })}>
          <option value="">Tous les types</option>
          {Object.entries(MOVE_KINDS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        {moves.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>
      <ErrorAlert error={moves.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        {moves.data && <MovesTable moves={moves.data.items} />}
        {moves.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <History className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun mouvement</p>
          </div>
        )}
        {moves.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={moves.data?.total ?? 0} noun={['mouvement', 'mouvements']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
    </>
  )
}

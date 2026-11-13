import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useDebounced } from '@/lib/useDebounced'
import { cn } from '@/lib/utils'
import type { ArticleListItem, Page } from '@/pages/catalog/types'
import { ADJUST_REASONS, dotAgeYears, dotLabel, fmtCost, fmtQty, MOVE_KINDS, type ArticleBrief, type Move } from '@/pages/inventory/types'

/** DOT avec son âge : gris jusqu'à 3 ans, orange de 3 à 5 ans (à écouler), rouge au-delà. */
export function DotBadge({ dot }: { dot: string | null | undefined }) {
  if (!dot) return <span className="text-muted-foreground">—</span>
  const age = dotAgeYears(dot)
  const variant = age >= 5 ? 'destructive' : age >= 3 ? 'accent' : 'secondary'
  return (
    <Badge variant={variant} className="font-mono" title={`${dotLabel(dot)} — ${age < 1 ? "moins d'un an" : `${Math.floor(age)} an${age >= 2 ? 's' : ''}`}`}>
      {dot}
    </Badge>
  )
}

const KIND_VARIANT = { reception: 'success', transfert: 'secondary', inventaire: 'accent', ajustement: 'outline' } as const

export function MoveKindBadge({ move }: { move: Move }) {
  return <Badge variant={KIND_VARIANT[move.kind]}>{MOVE_KINDS[move.kind]}</Badge>
}

/** Lien vers la pièce d'origine d'un mouvement (réception → commande, inventaire…). */
function MoveSource({ move }: { move: Move }) {
  const [type, id] = (move.source ?? '').split(':')
  if (type === 'count') return <Link to={`/stock/inventaires/${id}`} className="font-mono text-xs hover:underline">{move.reference}</Link>
  if (type === 'transfer') return <Link to={`/stock?vue=transferts&transfert=${id}`} className="font-mono text-xs hover:underline">{move.reference}</Link>
  if (move.reference) return <span className="font-mono text-xs">{move.reference}</span>
  return <span className="text-xs text-muted-foreground">{move.reason ? ADJUST_REASONS[move.reason as keyof typeof ADJUST_REASONS] ?? move.reason : '—'}</span>
}

export function MovesTable({ moves, showArticle = true }: { moves: Move[]; showArticle?: boolean }) {
  return (
    <table className="w-full text-sm">
      <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
        <tr>
          <th className="px-4 py-2.5 font-medium">Date</th>
          <th className="px-4 py-2.5 font-medium">Type</th>
          {showArticle && <th className="px-4 py-2.5 font-medium">Article</th>}
          <th className="hidden px-4 py-2.5 font-medium md:table-cell">Dépôt · emplacement</th>
          <th className="px-4 py-2.5 font-medium">DOT</th>
          <th className="px-4 py-2.5 text-right font-medium">Quantité</th>
          <th className="hidden px-4 py-2.5 text-right font-medium lg:table-cell">Coût unit.</th>
          <th className="px-4 py-2.5 font-medium">Pièce / motif</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {moves.map((m) => {
          const q = Number(m.quantity)
          return (
            <tr key={m.id}>
              <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">{formatDateTime(m.moved_at)}</td>
              <td className="px-4 py-2.5">
                <MoveKindBadge move={m} />
              </td>
              {showArticle && (
                <td className="px-4 py-2.5">
                  <Link to={`/articles/${m.article.id}`} className="font-medium hover:underline">
                    {m.article.designation}
                  </Link>
                  <span className="block font-mono text-xs text-muted-foreground">{m.article.code}</span>
                </td>
              )}
              <td className="hidden px-4 py-2.5 md:table-cell">
                {m.site.name} · <span className="font-mono text-xs">{m.location.code}</span>
              </td>
              <td className="px-4 py-2.5">
                <DotBadge dot={m.dot} />
              </td>
              <td className={cn('px-4 py-2.5 text-right font-medium tabular-nums', q > 0 ? 'text-emerald-700' : 'text-destructive')}>
                {q > 0 ? '+' : ''}
                {fmtQty(m.quantity)}
              </td>
              <td className="hidden px-4 py-2.5 text-right text-muted-foreground tabular-nums lg:table-cell">{fmtCost(m.unit_cost)}</td>
              <td className="px-4 py-2.5" title={m.note ?? undefined}>
                <MoveSource move={m} />
                {m.note && <span className="block max-w-48 truncate text-xs text-muted-foreground italic">{m.note}</span>}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** Recherche d'un article du catalogue (désignation, dimension, EAN…). */
export function ArticleSearch({ onPick, label = 'Chercher un article' }: { onPick: (a: ArticleBrief) => void; label?: string }) {
  const [search, setSearch] = useState('')
  const q = useDebounced(search.trim())
  const params = new URLSearchParams({ limit: '8', active: 'true' })
  if (q) params.set('q', q)
  const results = useQuery({
    queryKey: ['articles', 'stock-picker', params.toString()],
    queryFn: () => api<Page<ArticleListItem>>(`/catalog/articles?${params}`),
    enabled: q.length >= 2,
  })
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input autoFocus aria-label={label} placeholder="Désignation, dimension (2055516), EAN, code…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {q.length >= 2 && (
        <ul className="max-h-60 divide-y overflow-auto rounded-lg border">
          {results.data?.items.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-secondary/50"
                onClick={() => onPick({ id: a.id, code: a.code, designation: a.designation, ean: a.ean, brand: a.brand, size: a.size })}
              >
                <span className="font-medium">{a.designation}</span>
                <span className="text-xs text-muted-foreground">{[a.code, a.brand, a.ean].filter(Boolean).join(' · ')}</span>
              </button>
            </li>
          ))}
          {results.data?.total === 0 && <li className="px-3 py-3 text-center text-sm text-muted-foreground">Aucun article</li>}
          {results.isPending && (
            <li className="flex justify-center py-3">
              <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
            </li>
          )}
        </ul>
      )}
    </div>
  )
}

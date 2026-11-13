import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle, PackagePlus, Plus, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api, ApiError } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { cn } from '@/lib/utils'
import type { ArticleListItem, Page } from '@/pages/catalog/types'
import { money, type Order, type OrderLine } from '@/pages/purchasing/types'

const num = (v: string) => v.replace(',', '.').trim()
const decimalOk = (v: string, decimals: number) => new RegExp(`^\\d{1,11}([.,]\\d{1,${decimals}})?$`).test(v.trim())
const show = (v: string) => String(Number(v)).replace('.', ',')

/** Lignes d'une commande en brouillon : modifiables directement dans le tableau. */
export function LinesEditor({ order, onChange }: { order: Order; onChange: (o: Order) => void }) {
  const [adding, setAdding] = useState<'article' | 'libre' | null>(order.lines.length ? null : 'article')
  const remove = useMutation({
    mutationFn: (l: OrderLine) => api<Order>(`/purchasing/orders/${order.id}/lines/${l.id}`, { method: 'DELETE' }),
    onSuccess: onChange,
  })
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="w-10 px-3 py-2.5 font-medium">#</th>
              <th className="px-3 py-2.5 font-medium">Désignation</th>
              <th className="w-24 px-3 py-2.5 text-right font-medium">Quantité</th>
              <th className="w-32 px-3 py-2.5 text-right font-medium">P.U. HT</th>
              <th className="w-24 px-3 py-2.5 text-right font-medium">Remise %</th>
              <th className="w-32 px-3 py-2.5 text-right font-medium">Total HT</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {order.lines.map((l) => (
              <LineRow key={`${l.id}-${order.version}`} order={order} line={l} onChange={onChange} onDelete={() => remove.mutate(l)} />
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t bg-secondary/30">
              <td colSpan={5} className="px-3 py-2.5 text-right font-medium">
                Total HT
              </td>
              <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{money(order.total_ht)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <ErrorAlert error={remove.error} />
      {adding === 'article' && <ArticlePicker order={order} onAdded={onChange} onClose={() => setAdding(null)} />}
      {adding === 'libre' && <FreeLine order={order} onAdded={onChange} onClose={() => setAdding(null)} />}
      {!adding && (
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setAdding('article')}>
            <PackagePlus /> Ajouter un article
          </Button>
          <Button variant="ghost" onClick={() => setAdding('libre')}>
            <Plus /> Ligne libre (port, prestation…)
          </Button>
        </div>
      )}
    </div>
  )
}

function LineRow({ order, line, onChange, onDelete }: { order: Order; line: OrderLine; onChange: (o: Order) => void; onDelete: () => void }) {
  const [q, setQ] = useState(show(line.quantity))
  const [p, setP] = useState(show(line.unit_price))
  const [d, setD] = useState(show(line.discount_pct))
  const valid = decimalOk(q, 3) && Number(num(q)) > 0 && decimalOk(p, 4) && decimalOk(d, 2) && Number(num(d)) <= 100
  const save = useMutation({
    mutationFn: () =>
      api<Order>(`/purchasing/orders/${order.id}/lines/${line.id}`, {
        method: 'PUT',
        body: { article_id: line.article_id, designation: line.designation, supplier_ref: line.supplier_ref, quantity: num(q), unit_price: num(p), discount_pct: num(d) },
      }),
    onSuccess: onChange,
  })
  const changed = Number(num(q)) !== Number(line.quantity) || Number(num(p)) !== Number(line.unit_price) || Number(num(d)) !== Number(line.discount_pct)
  const commit = () => valid && changed && !save.isPending && save.mutate()
  const cell = (value: string, set: (v: string) => void, label: string) => (
    <Input
      aria-label={`${label} ligne ${line.line_no}`}
      inputMode="decimal"
      className={cn('h-8 text-right tabular-nums', !valid && 'border-destructive')}
      value={value}
      onChange={(e) => set(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
    />
  )
  return (
    <tr className="align-top">
      <td className="px-3 py-2.5 text-xs text-muted-foreground">{line.line_no}</td>
      <td className="px-3 py-2.5">
        <p className="font-medium">{line.designation}</p>
        <p className="font-mono text-xs text-muted-foreground">{line.supplier_ref ?? (line.article_id ? '' : 'ligne libre')}</p>
        {save.error instanceof ApiError && <p className="text-xs text-destructive">{save.error.message}</p>}
      </td>
      <td className="px-3 py-2">{cell(q, setQ, 'Quantité')}</td>
      <td className="px-3 py-2">{cell(p, setP, 'Prix')}</td>
      <td className="px-3 py-2">{cell(d, setD, 'Remise')}</td>
      <td className="px-3 py-2.5 text-right font-medium tabular-nums">{save.isPending ? <LoaderCircle className="ml-auto size-4 animate-spin" /> : money(line.line_total)}</td>
      <td className="px-1 py-1.5">
        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label={`Supprimer la ligne ${line.line_no}`} onClick={onDelete}>
          <Trash2 />
        </Button>
      </td>
    </tr>
  )
}

function ArticlePicker({ order, onAdded, onClose }: { order: Order; onAdded: (o: Order) => void; onClose: () => void }) {
  const [search, setSearch] = useState('')
  const [all, setAll] = useState(false)
  const [pending, setPending] = useState<ArticleListItem | null>(null) // article sans prix chez ce fournisseur
  const [price, setPrice] = useState('')
  const q = useDebounced(search.trim())
  const params = new URLSearchParams({ limit: '12', active: 'true' })
  if (q) params.set('q', q)
  if (!all) params.set('partner_id', String(order.supplier.id))
  const results = useQuery({
    queryKey: ['articles', 'picker', order.supplier.id, params.toString()],
    queryFn: () => api<Page<ArticleListItem>>(`/catalog/articles?${params}`),
  })
  const add = useMutation({
    mutationFn: (v: { article: ArticleListItem; price?: string }) =>
      api<Order>(`/purchasing/orders/${order.id}/lines`, { method: 'POST', body: { article_id: v.article.id, quantity: '1', unit_price: v.price ? num(v.price) : null } }),
    onSuccess: (o) => {
      setPending(null)
      setPrice('')
      onAdded(o)
    },
    onError: (error, v) => {
      // Article inconnu chez ce fournisseur : on demande le prix.
      if (error instanceof ApiError && error.message.startsWith('Prix inconnu')) setPending(v.article)
    },
  })
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input autoFocus aria-label="Chercher un article à commander" placeholder="Désignation, dimension (205/55R16), EAN, référence…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="accent-[var(--primary)]" />
          Tout le catalogue (pas seulement les articles de {order.supplier.name})
        </label>
        <Button variant="ghost" className="ml-auto" onClick={onClose}>
          Fermer
        </Button>
      </div>
      {pending && (
        <div className="flex flex-wrap items-end gap-3 rounded-lg bg-amber-500/10 p-3 text-sm">
          <p className="w-full text-amber-900">
            « {pending.designation} » n'a pas de prix chez {order.supplier.name} : indiquez le prix d'achat HT.
          </p>
          <Input aria-label="Prix d'achat HT" inputMode="decimal" className="w-40" value={price} onChange={(e) => setPrice(e.target.value)} autoFocus />
          <Button disabled={!decimalOk(price, 4) || add.isPending} onClick={() => add.mutate({ article: pending, price })}>
            Ajouter
          </Button>
          <Button variant="ghost" onClick={() => setPending(null)}>
            Annuler
          </Button>
        </div>
      )}
      {add.error && !pending && <ErrorAlert error={add.error} />}
      <ul className="divide-y rounded-lg border">
        {results.data?.items.map((a) => (
          <li key={a.id}>
            <button
              type="button"
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-secondary/50 disabled:opacity-50"
              disabled={add.isPending}
              onClick={() => add.mutate({ article: a })}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{a.designation}</span>
                <span className="block text-xs text-muted-foreground">{[a.brand, a.size, a.ean].filter(Boolean).join(' · ')}</span>
              </span>
              {!all && <span className="text-xs text-muted-foreground">chez ce fournisseur</span>}
              <Plus className="size-4 text-primary" />
            </button>
          </li>
        ))}
        {results.data?.total === 0 && (
          <li className="px-3 py-4 text-center text-sm text-muted-foreground">
            Aucun article{!all && ' chez ce fournisseur'}. {!all && 'Cochez « Tout le catalogue » pour élargir.'}
          </li>
        )}
        {results.isPending && (
          <li className="flex justify-center py-4">
            <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
          </li>
        )}
      </ul>
    </div>
  )
}

function FreeLine({ order, onAdded, onClose }: { order: Order; onAdded: (o: Order) => void; onClose: () => void }) {
  const [designation, setDesignation] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [price, setPrice] = useState('')
  const valid = designation.trim() && decimalOk(quantity, 3) && Number(num(quantity)) > 0 && decimalOk(price, 4)
  const add = useMutation({
    mutationFn: () => api<Order>(`/purchasing/orders/${order.id}/lines`, { method: 'POST', body: { designation: designation.trim(), quantity: num(quantity), unit_price: num(price) } }),
    onSuccess: (o) => {
      onAdded(o)
      onClose()
    },
  })
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4 shadow-xs">
      <label className="grid min-w-64 flex-1 gap-1 text-sm">
        Désignation
        <Input autoFocus value={designation} onChange={(e) => setDesignation(e.target.value)} placeholder="Frais de port, montage, palette…" />
      </label>
      <label className="grid w-28 gap-1 text-sm">
        Quantité
        <Input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
      </label>
      <label className="grid w-36 gap-1 text-sm">
        P.U. HT (€)
        <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
      </label>
      <Button disabled={!valid || add.isPending} onClick={() => add.mutate()}>
        Ajouter
      </Button>
      <Button variant="ghost" onClick={onClose}>
        Annuler
      </Button>
      {add.error && <ErrorAlert error={add.error} />}
    </div>
  )
}

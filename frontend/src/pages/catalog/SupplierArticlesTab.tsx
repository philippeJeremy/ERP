import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Boxes, FileUp, LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { formatPrice, type ArticleSupplier, type Page } from '@/pages/catalog/types'

const PAGE_SIZE = 25

/** Onglet « Articles » de la fiche fournisseur : ce qu'on lui achète, et à quel prix. */
export function SupplierArticlesTab({ partnerId }: { partnerId: number }) {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('actifs')
  const [page, setPage] = useState(0)
  const q = useDebounced(search.trim())
  const query = new URLSearchParams({ partner_id: String(partnerId), limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (q) query.set('q', q)
  if (status !== 'tous') query.set('discontinued', String(status === 'arretes'))
  const list = useQuery({
    queryKey: ['article-suppliers', company?.id, 'partner', query.toString()],
    queryFn: () => api<Page<ArticleSupplier>>(`/catalog/article-suppliers?${query}`),
    placeholderData: keepPreviousData,
  })

  if (!can(me?.permissions, 'catalog:read')) {
    return <p className="pt-6 pb-12 text-center text-sm text-muted-foreground">Vous n'avez pas le droit de voir le catalogue.</p>
  }
  return (
    <div className="space-y-4 pb-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Rechercher un article du fournisseur"
            placeholder="Désignation, référence, EAN…"
            className="pl-9"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
          />
        </div>
        <NativeSelect aria-label="Statut" className="w-auto" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0) }}>
          <option value="actifs">Actifs</option>
          <option value="arretes">Arrêtés</option>
          <option value="tous">Tous</option>
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        {can(me?.permissions, 'catalog:import') && (
          <Button variant="outline" className="ml-auto" asChild>
            <Link to={`/articles/imports/nouveau?fournisseur=${partnerId}`}>
              <FileUp /> Importer son tarif
            </Link>
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error} />
      {list.data && list.data.total === 0 && !q ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <Boxes className="size-8 text-muted-foreground/60" />
          <p className="font-medium">Aucun article {status === 'arretes' ? 'arrêté' : 'chez ce fournisseur'}</p>
          <p className="max-w-md text-sm text-muted-foreground">Importez son fichier tarif, ou ajoutez-le comme fournisseur depuis la fiche d'un article.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Référence</th>
                <th className="px-4 py-2.5 font-medium">Article</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Dimension</th>
                <th className="px-4 py-2.5 text-right font-medium">Prix d'achat HT</th>
                <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Mis à jour</th>
                <th className="px-4 py-2.5 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {list.data?.items.map((l) => (
                <tr key={l.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/articles/${l.article.id}`)}>
                  <td className="px-4 py-3 font-mono text-xs">{l.supplier_ref ?? '—'}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium">{l.article.designation}</p>
                    <p className="text-xs text-muted-foreground">{[l.article.brand, l.article.ean].filter(Boolean).join(' · ')}</p>
                  </td>
                  <td className="hidden px-4 py-3 font-mono text-xs md:table-cell">{l.article.size ?? '—'}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">{formatPrice(l.purchase_price)}</td>
                  <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{l.price_updated_at ? formatDateTime(l.price_updated_at) : '—'}</td>
                  <td className="px-4 py-3">
                    {l.is_discontinued ? <Badge variant="outline">Arrêté</Badge> : <Badge variant="success">Actif</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['article', 'articles']} onPage={setPage} />
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { AdjustDialog } from '@/pages/inventory/AdjustDialog'
import { DotBadge, MovesTable } from '@/pages/inventory/parts'
import { fmtCost, fmtMoney, fmtQty, type ArticleStock } from '@/pages/inventory/types'

/** Le stock d'un article (fiche article) : où, quels DOT, à quel coût, derniers mouvements. */
export function ArticleStockSection({ articleId }: { articleId: number }) {
  const { me, company } = useAuth()
  const canManage = can(me?.permissions, 'inventory:manage')
  const [adjust, setAdjust] = useState<{ siteId?: number; locationId?: number; dot?: string } | null>(null)
  const stock = useQuery({
    queryKey: ['article-stock', company?.id, articleId],
    queryFn: () => api<ArticleStock>(`/inventory/articles/${articleId}`),
  })
  const s = stock.data
  return (
    <section className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Stock</h2>
        {canManage && s && (
          <Button size="sm" variant="outline" onClick={() => setAdjust({})}>
            <SlidersHorizontal /> Ajuster
          </Button>
        )}
      </div>
      <ErrorAlert error={stock.error} />
      {stock.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {s && (
        <>
          <div className="mb-3 grid gap-3 sm:grid-cols-3">
            {[
              ['En stock', Number(s.reserved) ? `${fmtQty(s.quantity)} (dont ${fmtQty(s.reserved)} réservés)` : fmtQty(s.quantity)],
              ['Coût moyen pondéré', fmtCost(s.average_cost)],
              ['Valeur du stock', fmtMoney(s.value)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border bg-card p-4 shadow-xs">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
              </div>
            ))}
          </div>
          {s.sites.some((x) => Number(x.reserved)) && (
            <div className="mb-3 flex flex-wrap gap-2 text-sm">
              {s.sites.map((x) => (
                <span key={x.site.id} className="rounded-lg border bg-card px-3 py-1.5">
                  {x.site.name} : {fmtQty(x.quantity)} en stock, {fmtQty(x.reserved)} réservés,{' '}
                  <b className={Number(x.available) < 0 ? 'text-destructive' : undefined}>{fmtQty(x.available)} disponibles</b>
                </span>
              ))}
            </div>
          )}
          <div className="mb-4 overflow-x-auto rounded-xl border bg-card shadow-xs">
            <table className="w-full text-sm">
              <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Dépôt</th>
                  <th className="px-4 py-2.5 font-medium">Emplacement</th>
                  <th className="px-4 py-2.5 font-medium">DOT (le plus ancien d'abord)</th>
                  <th className="px-4 py-2.5 text-right font-medium">Quantité</th>
                  {canManage && <th className="w-24" />}
                </tr>
              </thead>
              <tbody className="divide-y">
                {s.levels.map((l) => (
                  <tr key={`${l.location.id}-${l.dot}`}>
                    <td className="px-4 py-2.5">{l.site.name}</td>
                    <td className="px-4 py-2.5 font-mono text-xs">{l.location.code}</td>
                    <td className="px-4 py-2.5">
                      <DotBadge dot={l.dot} />
                    </td>
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums">{fmtQty(l.quantity)}</td>
                    {canManage && (
                      <td className="px-2 py-1.5 text-right">
                        <Button variant="ghost" size="sm" onClick={() => setAdjust({ siteId: l.site.id, locationId: l.location.id, dot: l.dot })}>
                          Ajuster
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {s.levels.length === 0 && <p className="px-4 py-6 text-center text-sm text-muted-foreground">Pas de stock dans {company?.name}.</p>}
          </div>
          {s.moves.length > 0 && (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Derniers mouvements</h3>
                <Link to={`/stock?vue=mouvements&article=${articleId}`} className="text-sm text-primary hover:underline">
                  Tout le journal
                </Link>
              </div>
              <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
                <MovesTable moves={s.moves} showArticle={false} />
              </div>
            </>
          )}
        </>
      )}
      {adjust && s && <AdjustDialog article={s.article} {...adjust} onClose={() => setAdjust(null)} />}
    </section>
  )
}

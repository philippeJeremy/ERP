import { Pencil, Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { DotBadge } from '@/pages/inventory/parts'
import { fmtMoney, fmtQty } from '@/pages/inventory/types'
import { fmtPct, type OrderLine, type Quote, type SalesLine } from '@/pages/sales/types'

/** Les lignes d'un devis ou d'une commande. Pour une commande : livré, reste, stock. */
export function SalesLinesTable({
  lines,
  editable,
  order,
  onAdd,
  onEdit,
  onDelete,
}: {
  lines: (SalesLine | OrderLine)[]
  editable: boolean
  order?: boolean
  onAdd: () => void
  onEdit: (line: SalesLine | OrderLine) => void
  onDelete: (line: SalesLine | OrderLine) => void
}) {
  return (
    <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
      <table className="w-full text-sm">
        <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-10 px-3 py-2.5 font-medium">#</th>
            <th className="px-3 py-2.5 font-medium">Désignation</th>
            <th className="px-3 py-2.5 text-right font-medium">Qté</th>
            <th className="hidden px-3 py-2.5 text-right font-medium md:table-cell">P.U. HT</th>
            <th className="hidden px-3 py-2.5 text-right font-medium md:table-cell">Remise</th>
            <th className="hidden px-3 py-2.5 text-right font-medium lg:table-cell">Éco</th>
            <th className="px-3 py-2.5 text-right font-medium">Total HT</th>
            {order && <th className="px-3 py-2.5 text-right font-medium">Livré / stock</th>}
            <th className="hidden px-3 py-2.5 text-right font-medium xl:table-cell">Marge</th>
            {editable && <th className="w-20" />}
          </tr>
        </thead>
        <tbody className="divide-y">
          {lines.map((l) => {
            const o = order ? (l as OrderLine) : null
            const short = o && o.on_hand !== null && Number(o.remaining_qty) > Number(o.on_hand)
            return (
              <tr key={l.id}>
                <td className="px-3 py-2.5 text-muted-foreground tabular-nums">{l.line_no}</td>
                <td className="px-3 py-2.5">
                  {l.article ? (
                    <Link to={`/articles/${l.article.id}`} className="font-medium hover:underline">
                      {l.designation}
                    </Link>
                  ) : (
                    <span className="font-medium">{l.designation}</span>
                  )}
                  <span className="block text-xs text-muted-foreground">
                    {l.article ? <span className="font-mono">{l.article.code}</span> : 'Ligne libre'}
                    {o?.dot && (
                      <span className="ml-2">
                        DOT demandé <DotBadge dot={o.dot} />
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtQty(l.quantity)}</td>
                <td className="hidden px-3 py-2.5 text-right tabular-nums md:table-cell">{fmtMoney(l.unit_price)}</td>
                <td className="hidden px-3 py-2.5 text-right text-muted-foreground tabular-nums md:table-cell">{Number(l.discount_pct) ? fmtPct(l.discount_pct) : ''}</td>
                <td className="hidden px-3 py-2.5 text-right text-muted-foreground tabular-nums lg:table-cell">{Number(l.eco_total) ? fmtMoney(l.eco_total) : ''}</td>
                <td className="px-3 py-2.5 text-right font-medium tabular-nums">{fmtMoney(Number(l.line_total) + Number(l.eco_total))}</td>
                {o && (
                  <td className="px-3 py-2.5 text-right text-xs whitespace-nowrap tabular-nums">
                    {fmtQty(o.delivered_qty)} / {fmtQty(o.quantity)}
                    {o.on_hand !== null && Number(o.remaining_qty) > 0 && (
                      <span className={cn('block', short ? 'font-medium text-destructive' : 'text-muted-foreground')}>
                        {short ? 'Rupture : ' : 'Stock '}
                        {fmtQty(o.on_hand)}
                      </span>
                    )}
                  </td>
                )}
                <td className={cn('hidden px-3 py-2.5 text-right text-xs tabular-nums xl:table-cell', l.margin && Number(l.margin) < 0 ? 'text-destructive' : 'text-muted-foreground')}>
                  {l.margin !== null ? fmtMoney(l.margin) : ''}
                </td>
                {editable && (
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon" aria-label={`Modifier la ligne ${l.line_no}`} onClick={() => onEdit(l)}>
                      <Pencil />
                    </Button>
                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label={`Supprimer la ligne ${l.line_no}`} onClick={() => onDelete(l)}>
                      <Trash2 />
                    </Button>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
      {lines.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune ligne pour le moment.</p>}
      {editable && (
        <div className="border-t p-3">
          <Button variant="outline" size="sm" onClick={onAdd}>
            <Plus /> Ajouter une ligne
          </Button>
        </div>
      )}
    </div>
  )
}

/** Totaux : HT (dont éco-contribution), TVA par taux, TTC, et la marge (interne). */
export function DocTotals({ doc }: { doc: Pick<Quote, 'total_ht' | 'total_eco' | 'total_vat' | 'total_ttc' | 'vat' | 'margin' | 'lines'> }) {
  const margin = doc.margin !== null ? Number(doc.margin) : null
  // Taux de marge sur les seules lignes articles (les prestations n'ont pas de coût connu).
  const base = doc.lines.filter((l) => l.margin !== null).reduce((sum, l) => sum + Number(l.line_total), 0)
  return (
    <div className="ml-auto w-full max-w-sm space-y-1.5 rounded-xl border bg-card p-4 text-sm shadow-xs">
      <Row label="Total HT" value={fmtMoney(doc.total_ht)} />
      {Number(doc.total_eco) > 0 && <Row label="dont éco-contribution" value={fmtMoney(doc.total_eco)} muted />}
      {doc.vat.map((v) => (
        <Row key={v.rate} label={`TVA ${fmtPct(v.rate)}`} value={fmtMoney(v.vat)} muted />
      ))}
      <div className="border-t pt-1.5">
        <Row label="Total TTC" value={fmtMoney(doc.total_ttc)} strong />
      </div>
      {margin !== null && (
        <p className="pt-1 text-right text-xs text-muted-foreground">
          Marge au coût moyen :{' '}
          <Badge variant={margin < 0 ? 'destructive' : 'secondary'}>
            {fmtMoney(margin)}
            {base > 0 && ` · ${fmtPct(((margin / base) * 100).toFixed(1))}`}
          </Badge>
        </p>
      )}
    </div>
  )
}

function Row({ label, value, muted, strong }: { label: string; value: string; muted?: boolean; strong?: boolean }) {
  return (
    <div className={cn('flex justify-between', muted && 'text-muted-foreground', strong && 'text-base font-semibold')}>
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}

export function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-xs">
      <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      <div className="space-y-1 text-sm">{children}</div>
    </div>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ArticleSearch } from '@/pages/inventory/parts'
import { DOT_RE, fmtMoney, fmtQty, type ArticleBrief } from '@/pages/inventory/types'
import type { OrderLine, Pricing, SalesLine } from '@/pages/sales/types'

const NUM = /^\d{1,11}([.,]\d{1,4})?$/
const dec = (v: string) => v.trim().replace(',', '.')
const show = (v: string | null | undefined) => (v === null || v === undefined ? '' : String(Number(v)).replace('.', ','))

export interface LineBody {
  article_id: number | null
  designation: string | null
  quantity: string
  unit_price: string | null
  discount_pct: string | null
  eco_fee: string | null
  vat_rate: string | null
  dot: string
}

/** Ajout ou modification d'une ligne de devis / commande. Pour un article, le prix du
 * tarif et la remise du client sont proposés (modifiables), avec le stock du dépôt. */
export function LineDialog({
  line,
  customerId,
  siteId,
  withDot,
  onSave,
  onClose,
}: {
  line: SalesLine | OrderLine | null
  customerId: number
  siteId: number
  withDot: boolean
  onSave: (body: LineBody) => Promise<unknown>
  onClose: () => void
}) {
  const { company } = useAuth()
  const [article, setArticle] = useState<ArticleBrief | null>(line?.article ?? null)
  const [free, setFree] = useState(line !== null && line.article === null)
  const [f, setF] = useState({
    designation: line?.designation ?? '',
    quantity: show(line?.quantity ?? '1'),
    unit_price: show(line?.unit_price),
    discount_pct: show(line?.discount_pct),
    eco_fee: show(line?.eco_fee),
    vat_rate: show(line?.vat_rate),
    dot: line && 'dot' in line ? line.dot : '',
  })
  const pricing = useQuery({
    queryKey: ['pricing', company?.id, customerId, article?.id, siteId],
    queryFn: () => api<Pricing>(`/sales/pricing?customer_id=${customerId}&article_id=${article!.id}&site_id=${siteId}`),
    enabled: !!article,
  })
  const p = pricing.data
  // Valeurs affichées : la saisie, sinon la proposition du tarif.
  const value = {
    unit_price: f.unit_price || show(p?.unit_price),
    discount_pct: f.discount_pct || show(p?.discount_pct ?? '0'),
    eco_fee: f.eco_fee || show(p?.eco_fee ?? '0'),
    vat_rate: f.vat_rate || show(p?.vat_rate ?? '20'),
  }
  const ok = (v: string) => v === '' || NUM.test(v.trim())
  const qty = Number(dec(f.quantity))
  const net = Number(dec(value.unit_price || '0')) * (1 - Number(dec(value.discount_pct || '0')) / 100)
  const margin = p && Number(p.average_cost) > 0 ? net - Number(p.average_cost) : null
  const valid =
    (article || (free && f.designation.trim())) &&
    NUM.test(f.quantity.trim()) &&
    qty > 0 &&
    value.unit_price !== '' &&
    Object.values(value).every(ok) &&
    (!withDot || DOT_RE.test(f.dot.trim()))
  const save = useMutation({
    mutationFn: () =>
      onSave({
        article_id: article?.id ?? null,
        designation: f.designation.trim() || null,
        quantity: dec(f.quantity),
        unit_price: dec(value.unit_price),
        discount_pct: dec(value.discount_pct || '0'),
        eco_fee: dec(value.eco_fee || '0'),
        vat_rate: dec(value.vat_rate || '20'),
        dot: f.dot.trim(),
      }),
    onSuccess: onClose,
  })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const choosing = !article && !free
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{line ? `Ligne ${line.line_no}` : 'Ajouter une ligne'}</DialogTitle>
          <DialogDescription>Un article du catalogue, ou une ligne libre (montage, équilibrage, port…).</DialogDescription>
        </DialogHeader>
        {choosing ? (
          <div className="space-y-3">
            <ArticleSearch onPick={setArticle} label="Article" />
            <Button variant="outline" size="sm" onClick={() => setFree(true)}>
              Ligne libre (prestation, port…)
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {article && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-secondary/30 px-3 py-2 text-sm">
                <span>
                  <span className="font-medium">{article.designation}</span>
                  <span className="block font-mono text-xs text-muted-foreground">{article.code}</span>
                </span>
                {p && (
                  <span className="text-xs">
                    Stock dépôt <b className="tabular-nums">{fmtQty(p.on_hand)}</b> · disponible{' '}
                    <b className={cn('tabular-nums', Number(p.available) < qty && 'text-destructive')}>{fmtQty(p.available)}</b>
                  </span>
                )}
                {!line && (
                  <Button variant="ghost" size="sm" onClick={() => setArticle(null)}>
                    Changer
                  </Button>
                )}
              </div>
            )}
            {p && p.unit_price === null && !f.unit_price && (
              <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">Pas de prix au tarif : saisissez un prix (ou complétez le tarif dans Ventes → Tarif).</p>
            )}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="sm:col-span-3">
                <Field id="ln_designation" label="Désignation" hint={article ? "Vide = celle de l'article" : undefined}>
                  <Input id="ln_designation" value={f.designation} placeholder={article?.designation} onChange={set('designation')} />
                </Field>
              </div>
              <Field id="ln_qty" label="Quantité">
                <Input id="ln_qty" inputMode="decimal" value={f.quantity} onChange={set('quantity')} />
              </Field>
              <Field id="ln_price" label="Prix unitaire HT" error={ok(value.unit_price) ? undefined : 'Montant invalide'}>
                <Input id="ln_price" inputMode="decimal" value={value.unit_price} onChange={set('unit_price')} />
              </Field>
              <Field id="ln_discount" label="Remise %">
                <Input id="ln_discount" inputMode="decimal" value={value.discount_pct} onChange={set('discount_pct')} />
              </Field>
              <Field id="ln_eco" label="Éco-contribution unitaire" hint="Pneus : filière de recyclage">
                <Input id="ln_eco" inputMode="decimal" value={value.eco_fee} onChange={set('eco_fee')} />
              </Field>
              <Field id="ln_vat" label="TVA %">
                <Input id="ln_vat" inputMode="decimal" value={value.vat_rate} onChange={set('vat_rate')} />
              </Field>
              {withDot && article && (
                <Field id="ln_dot" label="DOT demandé" hint="Vide = les plus anciens" error={DOT_RE.test(f.dot.trim()) ? undefined : 'DOT invalide'}>
                  <Input id="ln_dot" className="font-mono" maxLength={4} inputMode="numeric" value={f.dot} onChange={set('dot')} />
                </Field>
              )}
            </div>
            {qty > 0 && value.unit_price && (
              <p className="text-sm text-muted-foreground">
                Net : <b className="text-foreground">{fmtMoney(net)}</b> l'unité, soit <b className="text-foreground">{fmtMoney(net * qty)}</b> HT
                {margin !== null && (
                  <>
                    {' '}
                    · marge au CMP <b className={cn(margin < 0 ? 'text-destructive' : 'text-emerald-700')}>{fmtMoney(margin * qty)}</b>
                  </>
                )}
              </p>
            )}
          </div>
        )}
        <ErrorAlert error={save.error ?? pricing.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            {line ? 'Enregistrer' : 'Ajouter'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

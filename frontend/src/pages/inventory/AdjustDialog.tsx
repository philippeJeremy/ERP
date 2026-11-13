import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { STOCK_KEYS, useLocations, useSites } from '@/pages/inventory/hooks'
import { ArticleSearch } from '@/pages/inventory/parts'
import { ADJUST_REASONS, DOT_RE, type ArticleBrief } from '@/pages/inventory/types'

const QTY_RE = /^\d{1,11}([.,]\d{1,3})?$/
const COST_RE = /^\d{1,10}([.,]\d{1,4})?$/

/** Ajustement manuel : sortie (casse, perte, vol…) ou entrée (erreur, retour client…). */
export function AdjustDialog({
  article: initial,
  siteId,
  locationId,
  dot: initialDot = '',
  onClose,
}: {
  article?: ArticleBrief
  siteId?: number
  locationId?: number
  dot?: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [article, setArticle] = useState<ArticleBrief | null>(initial ?? null)
  const sites = useSites()
  const [site, setSite] = useState(siteId ? String(siteId) : '')
  const siteValue = site || (sites.data?.[0] ? String(sites.data[0].id) : '')
  const locations = useLocations(siteValue ? Number(siteValue) : null)
  const [location, setLocation] = useState(locationId ? String(locationId) : '')
  const locationValue = locations.data?.some((l) => String(l.id) === location) ? location : locations.data?.[0] ? String(locations.data[0].id) : ''
  const [direction, setDirection] = useState<'out' | 'in'>('out')
  const [qty, setQty] = useState('1')
  const [dot, setDot] = useState(initialDot)
  const [reason, setReason] = useState<keyof typeof ADJUST_REASONS>('casse')
  const [cost, setCost] = useState('')
  const [note, setNote] = useState('')
  const qtyOk = QTY_RE.test(qty.trim()) && Number(qty.replace(',', '.')) > 0
  const costOk = cost.trim() === '' || COST_RE.test(cost.trim())
  const dotOk = DOT_RE.test(dot.trim())
  const save = useMutation({
    mutationFn: () =>
      api('/inventory/adjustments', {
        method: 'POST',
        body: {
          article_id: article!.id,
          location_id: Number(locationValue),
          dot: dot.trim(),
          quantity: (direction === 'out' ? '-' : '') + qty.trim().replace(',', '.'),
          reason,
          unit_cost: direction === 'in' && cost.trim() ? cost.trim().replace(',', '.') : null,
          note: note.trim() || null,
        },
      }),
    onSuccess: async () => {
      await Promise.all(STOCK_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Ajuster le stock</DialogTitle>
          <DialogDescription>Chaque ajustement est tracé au journal avec son motif. Une sortie part au coût moyen pondéré.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {article ? (
            <div className="flex items-center justify-between rounded-lg border bg-secondary/30 px-3 py-2 text-sm">
              <span>
                <span className="font-medium">{article.designation}</span>
                <span className="block font-mono text-xs text-muted-foreground">{article.code}</span>
              </span>
              {!initial && (
                <Button variant="ghost" size="sm" onClick={() => setArticle(null)}>
                  Changer
                </Button>
              )}
            </div>
          ) : (
            <ArticleSearch onPick={setArticle} label="Article à ajuster" />
          )}
          <div role="radiogroup" aria-label="Sens" className="grid grid-cols-2 gap-2">
            {(['out', 'in'] as const).map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={direction === d}
                onClick={() => {
                  setDirection(d)
                  setReason(d === 'out' ? 'casse' : 'erreur')
                }}
                className={cn('rounded-lg border px-3 py-2 text-sm font-medium', direction === d ? 'border-primary bg-primary/5' : 'text-muted-foreground')}
              >
                {d === 'out' ? '− Sortie' : '+ Entrée'}
              </button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="adj_site" label="Dépôt">
              <NativeSelect id="adj_site" value={siteValue} onChange={(e) => setSite(e.target.value)}>
                {sites.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="adj_location" label="Emplacement">
              <NativeSelect id="adj_location" value={locationValue} onChange={(e) => setLocation(e.target.value)}>
                {locations.data?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code}
                    {l.name ? ` — ${l.name}` : ''}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="adj_qty" label="Quantité" error={qtyOk ? undefined : 'Quantité invalide'}>
              <Input id="adj_qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
            </Field>
            <Field id="adj_dot" label="DOT" hint="Semaine + année, ex. 2324. Vide si sans DOT." error={dotOk ? undefined : 'DOT invalide'}>
              <Input id="adj_dot" className="font-mono" inputMode="numeric" maxLength={4} value={dot} onChange={(e) => setDot(e.target.value)} />
            </Field>
            <Field id="adj_reason" label="Motif">
              <NativeSelect id="adj_reason" value={reason} onChange={(e) => setReason(e.target.value as keyof typeof ADJUST_REASONS)}>
                {Object.entries(ADJUST_REASONS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {direction === 'in' && (
              <Field id="adj_cost" label="Coût unitaire HT" hint="Vide : au coût moyen actuel." error={costOk ? undefined : 'Montant invalide'}>
                <Input id="adj_cost" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
              </Field>
            )}
          </div>
          <Field id="adj_note" label="Commentaire">
            <Textarea id="adj_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!article || !locationValue || !qtyOk || !costOk || !dotOk || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer l'ajustement
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

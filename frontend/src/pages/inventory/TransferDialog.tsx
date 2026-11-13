import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { STOCK_KEYS, useLocations, useSites } from '@/pages/inventory/hooks'
import { ArticleSearch } from '@/pages/inventory/parts'
import { fmtQty, originOptions, type ArticleBrief, type ArticleStock, type Transfer } from '@/pages/inventory/types'

const QTY_RE = /^\d{1,11}([.,]\d{1,3})?$/
const today = () => new Date().toISOString().slice(0, 10)

interface Line {
  key: number
  article: ArticleBrief
  /** « id-emplacement|DOT », DOT « * » = les plus anciens d'abord. */
  origin: string
  qty: string
}

/** Choix de l'origine d'une ligne : un lot précis (emplacement + DOT), ou « les plus anciens ». */
function LineRow({ line, siteId, onChange, onRemove }: { line: Line; siteId: number; onChange: (l: Line) => void; onRemove: () => void }) {
  const { company } = useAuth()
  const stock = useQuery({
    queryKey: ['article-stock', company?.id, line.article.id],
    queryFn: () => api<ArticleStock>(`/inventory/articles/${line.article.id}`),
  })
  const options = originOptions(stock.data, siteId)
  const max = options.find((o) => o.value === line.origin)?.max ?? 0
  const qty = Number(line.qty.replace(',', '.'))
  const tooMuch = QTY_RE.test(line.qty) && qty > max
  return (
    <tr className="align-top">
      <td className="px-3 py-2">
        <span className="font-medium">{line.article.designation}</span>
        <span className="block font-mono text-xs text-muted-foreground">{line.article.code}</span>
      </td>
      <td className="px-3 py-1.5">
        {stock.isPending ? (
          <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
        ) : options.length ? (
          <NativeSelect aria-label={`Origine ${line.article.code}`} className="h-8" value={line.origin} onChange={(e) => onChange({ ...line, origin: e.target.value })}>
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </NativeSelect>
        ) : (
          <span className="text-sm text-destructive">Pas de stock dans ce dépôt</span>
        )}
      </td>
      <td className="w-28 px-3 py-1.5">
        <Input aria-label={`Quantité ${line.article.code}`} className="h-8 text-right" inputMode="decimal" value={line.qty} onChange={(e) => onChange({ ...line, qty: e.target.value })} />
        {tooMuch && <span className="text-xs text-destructive">max {fmtQty(max)}</span>}
      </td>
      <td className="w-10 px-1 py-1.5">
        <Button variant="ghost" size="icon" aria-label="Retirer la ligne" onClick={onRemove}>
          <Trash2 />
        </Button>
      </td>
    </tr>
  )
}

export function TransferDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (t: Transfer) => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const sites = useSites()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const fromValue = from || (sites.data?.[0] ? String(sites.data[0].id) : '')
  const toValue = to || (sites.data?.find((s) => String(s.id) !== fromValue) ? String(sites.data.find((s) => String(s.id) !== fromValue)!.id) : '')
  const targets = useLocations(toValue ? Number(toValue) : null)
  const [target, setTarget] = useState('')
  const [date, setDate] = useState(today())
  const [note, setNote] = useState('')
  const [lines, setLines] = useState<Line[]>([])
  const [adding, setAdding] = useState(true)
  const [nextKey, setNextKey] = useState(0)
  const valid = fromValue && toValue && fromValue !== toValue && lines.length > 0 && lines.every((l) => l.origin && QTY_RE.test(l.qty.trim()) && Number(l.qty.replace(',', '.')) > 0)
  const save = useMutation({
    mutationFn: () =>
      api<Transfer>('/inventory/transfers', {
        method: 'POST',
        body: {
          from_site_id: Number(fromValue),
          to_site_id: Number(toValue),
          transferred_on: date,
          note: note.trim() || null,
          lines: lines.map((l) => {
            const [location, dot] = l.origin.split('|')
            return {
              article_id: l.article.id,
              from_location_id: Number(location),
              to_location_id: target && targets.data?.some((t) => String(t.id) === target) ? Number(target) : null,
              dot: dot === '*' ? null : dot,
              quantity: l.qty.trim().replace(',', '.'),
            }
          }),
        },
      }),
    onSuccess: async (t) => {
      await Promise.all(STOCK_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
      onClose()
      onCreated(t)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Nouveau transfert entre dépôts</DialogTitle>
          <DialogDescription>Choisissez pour chaque article le lot à envoyer. « Les plus anciens d'abord » répartit automatiquement sur les DOT les plus vieux.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-4">
          <Field id="tr_from" label="Depuis">
            <NativeSelect
              id="tr_from"
              value={fromValue}
              onChange={(e) => {
                setFrom(e.target.value)
                setLines([])
              }}
            >
              {sites.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="tr_to" label="Vers">
            <NativeSelect id="tr_to" value={toValue} onChange={(e) => setTo(e.target.value)}>
              {sites.data
                ?.filter((s) => String(s.id) !== fromValue)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </NativeSelect>
          </Field>
          <Field id="tr_target" label="Emplacement d'arrivée">
            <NativeSelect id="tr_target" value={target} onChange={(e) => setTarget(e.target.value)}>
              {targets.data?.map((l) => (
                <option key={l.id} value={l.is_default ? '' : l.id}>
                  {l.code}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="tr_date" label="Date">
            <Input id="tr_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </div>
        {sites.data && sites.data.length < 2 && <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">Il faut au moins deux dépôts pour transférer du stock.</p>}
        {lines.length > 0 && (
          <div className="max-h-72 overflow-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Article</th>
                  <th className="px-3 py-2">Origine (emplacement · DOT)</th>
                  <th className="px-3 py-2">Quantité</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y">
                {lines.map((l) => (
                  <LineRow
                    key={l.key}
                    line={l}
                    siteId={Number(fromValue)}
                    onChange={(n) => setLines((all) => all.map((x) => (x.key === n.key ? n : x)))}
                    onRemove={() => setLines((all) => all.filter((x) => x.key !== l.key))}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {adding ? (
          <div className="rounded-lg border bg-secondary/20 p-3">
            <ArticleSearch
              label="Article à transférer"
              onPick={async (a) => {
                // On lit le stock de l'article pour proposer d'office le premier lot disponible.
                const stock = await queryClient.fetchQuery({
                  queryKey: ['article-stock', company?.id, a.id],
                  queryFn: () => api<ArticleStock>(`/inventory/articles/${a.id}`),
                })
                const origin = originOptions(stock, Number(fromValue))[0]?.value ?? ''
                setLines((all) => [...all, { key: nextKey, article: a, origin, qty: '1' }])
                setNextKey(nextKey + 1)
                setAdding(false)
              }}
            />
          </div>
        ) : (
          <Button variant="outline" className="w-fit" onClick={() => setAdding(true)}>
            <Plus /> Ajouter un article
          </Button>
        )}
        <Field id="tr_note" label="Note">
          <Textarea id="tr_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Transférer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

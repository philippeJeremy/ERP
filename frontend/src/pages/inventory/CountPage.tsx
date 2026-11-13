import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, LoaderCircle, Plus, Save, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { STOCK_KEYS, useLocations } from '@/pages/inventory/hooks'
import { ArticleSearch, DotBadge } from '@/pages/inventory/parts'
import { COUNT_STATUSES, DOT_RE, fmtMoney, fmtQty, type ArticleBrief, type Count } from '@/pages/inventory/types'

const QTY_RE = /^\d{1,11}([.,]\d{1,3})?$/
const toApi = (v: string) => (v.trim() === '' ? null : v.trim().replace(',', '.'))

export function CountPage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const queryClient = useQueryClient()
  const canCount = can(me?.permissions, 'inventory:count')
  const canManage = can(me?.permissions, 'inventory:manage')
  // Saisies non encore enregistrées : id de ligne → texte tapé.
  const [entries, setEntries] = useState<Record<number, string>>({})
  const [filter, setFilter] = useState<'all' | 'todo' | 'diff'>('all')
  const [adding, setAdding] = useState(false)
  const [validating, setValidating] = useState(false)
  const count = useQuery({ queryKey: ['count', company?.id, Number(id)], queryFn: () => api<Count>(`/inventory/counts/${id}`) })
  const done = (c: Count) => {
    queryClient.setQueryData(['count', company?.id, c.id], c)
    void queryClient.invalidateQueries({ queryKey: ['counts'] })
  }
  const save = useMutation({
    mutationFn: () =>
      api<Count>(`/inventory/counts/${id}/entries`, {
        method: 'PUT',
        body: { entries: Object.entries(entries).map(([lineId, v]) => ({ line_id: Number(lineId), counted_qty: toApi(v) })) },
      }),
    onSuccess: (c) => {
      setEntries({})
      done(c)
    },
  })
  const cancel = useMutation({
    mutationFn: () => api<Count>(`/inventory/counts/${id}/cancel`, { method: 'POST' }),
    onSuccess: done,
  })
  const c = count.data
  if (!c) {
    return (
      <>
        <ErrorAlert error={count.error} />
        {count.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      </>
    )
  }
  const open = c.status === 'en_cours'
  const dirty = Object.keys(entries).length > 0
  const badEntry = Object.values(entries).some((v) => v.trim() !== '' && !QTY_RE.test(v.trim()))
  const shown = c.lines.filter((l) => (filter === 'todo' ? l.counted_qty === null : filter === 'diff' ? l.difference !== null && Number(l.difference) !== 0 : true))
  const status = COUNT_STATUSES[c.status]
  return (
    <>
      <Link to="/stock?vue=inventaires" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Inventaires
      </Link>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-semibold">
            Inventaire <span className="font-mono">{c.number}</span> <Badge variant={status.variant}>{status.label}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            {c.site.name}
            {c.location ? ` · emplacement ${c.location.code}` : ' · tout le dépôt'} · ouvert le {formatDateTime(c.created_at)}
            {c.validated_at && ` · validé le ${formatDateTime(c.validated_at)}`}
          </p>
          {c.note && <p className="mt-1 text-sm italic">{c.note}</p>}
        </div>
        {open && (
          <div className="flex flex-wrap gap-2">
            {canManage && (
              <Button variant="outline" disabled={cancel.isPending} onClick={() => window.confirm("Annuler l'inventaire ? Le stock ne sera pas modifié.") && cancel.mutate()}>
                <XCircle /> Annuler
              </Button>
            )}
            {canManage && (
              <Button disabled={dirty} title={dirty ? "Enregistrez d'abord les comptages" : undefined} onClick={() => setValidating(true)}>
                <CheckCircle2 /> Valider
              </Button>
            )}
          </div>
        )}
      </div>
      <ErrorAlert error={cancel.error} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border bg-card p-4 shadow-xs">
          <p className="text-xs text-muted-foreground">Lignes comptées</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {c.counted_count} / {c.line_count}
          </p>
        </div>
        <div className="rounded-xl border bg-card p-4 shadow-xs">
          <p className="text-xs text-muted-foreground">Lignes en écart</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{c.lines.filter((l) => l.difference !== null && Number(l.difference) !== 0).length}</p>
        </div>
        <div className="rounded-xl border bg-card p-4 shadow-xs">
          <p className="text-xs text-muted-foreground">Valeur de l'écart (CMP)</p>
          <p className={cn('mt-1 text-2xl font-semibold tabular-nums', Number(c.value_difference) < 0 && 'text-destructive', Number(c.value_difference) > 0 && 'text-emerald-700')}>
            {fmtMoney(c.value_difference)}
          </p>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <NativeSelect aria-label="Filtrer les lignes" className="w-48" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
          <option value="all">Toutes les lignes</option>
          <option value="todo">À compter</option>
          <option value="diff">En écart</option>
        </NativeSelect>
        {open && canCount && (
          <>
            <Button variant="outline" onClick={() => setAdding(!adding)}>
              <Plus /> Article trouvé hors liste
            </Button>
            <Button className="ml-auto" disabled={!dirty || badEntry || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
              Enregistrer les comptages
            </Button>
          </>
        )}
      </div>
      <ErrorAlert error={save.error} />
      {adding && <AddLine count={c} onDone={(n) => {
            setAdding(false)
            done(n)
          }} />}
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Emplacement</th>
              <th className="px-4 py-2.5 font-medium">Article</th>
              <th className="px-4 py-2.5 font-medium">DOT</th>
              <th className="px-4 py-2.5 text-right font-medium">Théorique</th>
              <th className="w-32 px-4 py-2.5 font-medium">Compté</th>
              <th className="px-4 py-2.5 text-right font-medium">Écart</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {shown.map((l) => {
              const typed = entries[l.id]
              const value = typed ?? (l.counted_qty === null ? '' : fmtQty(l.counted_qty).replace(/\s/g, ''))
              const diff = l.difference === null ? null : Number(l.difference)
              return (
                <tr key={l.id} className={cn(typed !== undefined && 'bg-amber-500/5')}>
                  <td className="px-4 py-2 font-mono text-xs">{l.location.code}</td>
                  <td className="px-4 py-2">
                    <span className="font-medium">{l.article.designation}</span>
                    <span className="block font-mono text-xs text-muted-foreground">
                      {l.article.code}
                      {l.article.ean && ` · ${l.article.ean}`}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <DotBadge dot={l.dot} />
                  </td>
                  <td className="px-4 py-2 text-right text-muted-foreground tabular-nums">{fmtQty(l.expected_qty)}</td>
                  <td className="px-4 py-1.5">
                    {open && canCount ? (
                      <Input
                        aria-label={`Compté ${l.article.code} ${l.location.code} ${l.dot}`}
                        className={cn('h-8 text-right', typed !== undefined && typed.trim() !== '' && !QTY_RE.test(typed.trim()) && 'border-destructive')}
                        inputMode="decimal"
                        placeholder="—"
                        value={value}
                        onChange={(e) => setEntries({ ...entries, [l.id]: e.target.value })}
                      />
                    ) : (
                      <span className="tabular-nums">{l.counted_qty === null ? '—' : fmtQty(l.counted_qty)}</span>
                    )}
                  </td>
                  <td className={cn('px-4 py-2 text-right font-medium tabular-nums', diff !== null && diff < 0 && 'text-destructive', diff !== null && diff > 0 && 'text-emerald-700')}>
                    {diff === null ? '' : diff === 0 ? '=' : `${diff > 0 ? '+' : ''}${fmtQty(diff)}`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {shown.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune ligne.</p>}
      </div>
      {validating && <ValidateDialog count={c} onDone={(n) => {
            setValidating(false)
            done(n)
          }} onClose={() => setValidating(false)} />}
    </>
  )
}

function AddLine({ count, onDone }: { count: Count; onDone: (c: Count) => void }) {
  const [article, setArticle] = useState<ArticleBrief | null>(null)
  const locations = useLocations(count.site.id)
  const [location, setLocation] = useState(count.location ? String(count.location.id) : '')
  const locationValue = location || (locations.data?.[0] ? String(locations.data[0].id) : '')
  const [dot, setDot] = useState('')
  const [qty, setQty] = useState('1')
  const add = useMutation({
    mutationFn: () =>
      api<Count>(`/inventory/counts/${count.id}/lines`, {
        method: 'POST',
        body: { article_id: article!.id, location_id: Number(locationValue), dot: dot.trim(), counted_qty: qty.trim().replace(',', '.') },
      }),
    onSuccess: onDone,
  })
  return (
    <div className="mb-4 space-y-3 rounded-xl border bg-card p-4 shadow-xs">
      {article ? (
        <p className="text-sm">
          <span className="font-medium">{article.designation}</span> <span className="font-mono text-xs text-muted-foreground">{article.code}</span>{' '}
          <Button variant="ghost" size="sm" onClick={() => setArticle(null)}>
            Changer
          </Button>
        </p>
      ) : (
        <ArticleSearch onPick={setArticle} label="Article trouvé" />
      )}
      <div className="grid gap-3 sm:grid-cols-4">
        <Field id="add_location" label="Emplacement">
          <NativeSelect id="add_location" value={locationValue} disabled={!!count.location} onChange={(e) => setLocation(e.target.value)}>
            {locations.data?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.code}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field id="add_dot" label="DOT" error={DOT_RE.test(dot.trim()) ? undefined : 'DOT invalide'}>
          <Input id="add_dot" className="font-mono" maxLength={4} inputMode="numeric" value={dot} onChange={(e) => setDot(e.target.value)} />
        </Field>
        <Field id="add_qty" label="Quantité comptée">
          <Input id="add_qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
        </Field>
        <div className="flex items-end">
          <Button disabled={!article || !DOT_RE.test(dot.trim()) || !QTY_RE.test(qty.trim()) || add.isPending} onClick={() => add.mutate()}>
            Ajouter
          </Button>
        </div>
      </div>
      <ErrorAlert error={add.error} />
    </div>
  )
}

function ValidateDialog({ count, onDone, onClose }: { count: Count; onDone: (c: Count) => void; onClose: () => void }) {
  const queryClient = useQueryClient()
  const uncounted = count.lines.filter((l) => l.counted_qty === null).length
  const [asZero, setAsZero] = useState(false)
  const diffs = count.lines.filter((l) => l.difference !== null && Number(l.difference) !== 0).length
  const validate = useMutation({
    mutationFn: () => api<Count>(`/inventory/counts/${count.id}/validate`, { method: 'POST', body: { version: count.version, uncounted_as_zero: asZero } }),
    onSuccess: async (c) => {
      await Promise.all(STOCK_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
      onDone(c)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Valider l'inventaire {count.number}</DialogTitle>
          <DialogDescription>
            {diffs} ligne{diffs > 1 ? 's' : ''} en écart, pour {fmtMoney(count.value_difference)} au coût moyen. Chaque écart devient un mouvement de stock ; c'est définitif.
          </DialogDescription>
        </DialogHeader>
        {uncounted > 0 && (
          <CheckRow
            checked={asZero}
            onChange={setAsZero}
            title={`Considérer les ${uncounted} ligne${uncounted > 1 ? 's' : ''} non comptée${uncounted > 1 ? 's' : ''} à zéro`}
            description="Sinon, comptez-les d'abord. À zéro, leur stock théorique sera sorti."
          />
        )}
        <ErrorAlert error={validate.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={(uncounted > 0 && !asZero) || validate.isPending} onClick={() => validate.mutate()}>
            {validate.isPending && <LoaderCircle className="animate-spin" />}
            Valider l'inventaire
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

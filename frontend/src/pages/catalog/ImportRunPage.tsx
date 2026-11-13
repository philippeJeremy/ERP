import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, CheckCircle2, FileSpreadsheet, LoaderCircle, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { formatPrice, formatSize, priceChange, RUN_STATUSES, type ImportLine, type ImportRun, type LineStatus, type Page } from '@/pages/catalog/types'

const PAGE_SIZE = 50
const CATEGORIES: { status: LineStatus; label: string; count: (r: ImportRun) => number; tone: string; hint: string }[] = [
  { status: 'nouveau', label: 'Nouveaux', count: (r) => r.new_count, tone: 'text-emerald-700', hint: 'Articles créés ou ajoutés chez ce fournisseur' },
  { status: 'maj', label: 'Prix modifiés', count: (r) => r.updated_count, tone: 'text-sky-700', hint: 'Le prix d’achat change' },
  { status: 'reactive', label: 'Réactivés', count: (r) => r.reactivated_count, tone: 'text-emerald-700', hint: 'Arrêtés, de retour dans le tarif' },
  { status: 'arret', label: 'Arrêtés', count: (r) => r.discontinued_count, tone: 'text-amber-700', hint: 'Absents du fichier complet' },
  { status: 'erreur', label: 'Erreurs', count: (r) => r.error_count, tone: 'text-destructive', hint: 'Lignes ignorées' },
  { status: 'inchange', label: 'Inchangés', count: (r) => r.unchanged_count, tone: 'text-muted-foreground', hint: 'Même prix' },
]

const str = (v: unknown) => (v === undefined || v === null || v === '' ? null : String(v))

export function ImportRunPage() {
  const { id } = useParams()
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<LineStatus | null>(null)
  const [page, setPage] = useState(0)
  const [confirming, setConfirming] = useState(false)

  const run = useQuery({
    queryKey: ['import', company?.id, Number(id)],
    queryFn: () => api<ImportRun>(`/catalog/imports/${id}`),
    // Analyse ou application en cours (dans le worker) : on interroge toutes les 1,5 s.
    refetchInterval: (q) => (q.state.data && ['analyse', 'application'].includes(q.state.data.status) ? 1500 : false),
  })
  const r = run.data
  // Catégorie affichée : celle choisie, sinon la première qui contient des lignes.
  const active = filter ?? CATEGORIES.find((c) => r && c.count(r) > 0)?.status ?? 'nouveau'
  const showLines = r && ['pret', 'termine', 'application'].includes(r.status)
  const lines = useQuery({
    queryKey: ['import-lines', company?.id, Number(id), active, page, r?.status],
    queryFn: () => api<Page<ImportLine>>(`/catalog/imports/${id}/lines?status=${active}&limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`),
    enabled: !!showLines,
  })
  const cancel = useMutation({
    mutationFn: () => api<ImportRun>(`/catalog/imports/${id}/cancel`, { method: 'POST' }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['import', company?.id, saved.id], saved)
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  if (run.isPending) return <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
  if (run.isError) return <ErrorAlert error={run.error} />
  const run_ = run.data

  return (
    <>
      <Link to="/articles/imports" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Imports tarifs
      </Link>
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            Tarif {run_.partner_name}
            <Badge variant={RUN_STATUSES[run_.status].variant}>{RUN_STATUSES[run_.status].label}</Badge>
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            <FileSpreadsheet className="size-4" /> {run_.filename} · {formatSize(run_.file_size)} · {run_.total_lines.toLocaleString('fr-FR')} lignes · déposé le{' '}
            {formatDateTime(run_.created_at)}
            {!run_.full_catalog && ' · fichier partiel (aucun arrêt)'}
          </p>
        </div>
        {run_.status === 'pret' && (
          <div className="flex gap-2">
            <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              Annuler l'import
            </Button>
            <Button onClick={() => setConfirming(true)}>Appliquer au catalogue</Button>
          </div>
        )}
      </div>
      <ErrorAlert error={cancel.error} />

      {run_.status === 'analyse' && (
        <Banner icon={<LoaderCircle className="size-5 animate-spin" />} title="Analyse du fichier en cours…">
          Chaque ligne est lue, contrôlée et comparée au catalogue. Rien n'est encore modifié.
        </Banner>
      )}
      {run_.status === 'application' && (
        <Banner icon={<LoaderCircle className="size-5 animate-spin" />} title="Application en cours…">
          Les articles et les prix sont mis à jour en une seule opération : tout ou rien.
        </Banner>
      )}
      {run_.status === 'pret' && (
        <Banner icon={<CheckCircle2 className="size-5 text-emerald-600" />} title="Analyse terminée : vérifiez avant d'appliquer">
          Rien n'a encore été modifié. Parcourez les catégories ci-dessous, puis appliquez ou annulez.
        </Banner>
      )}
      {run_.status === 'termine' && (
        <Banner icon={<CheckCircle2 className="size-5 text-emerald-600" />} title={`Appliqué le ${run_.applied_at ? formatDateTime(run_.applied_at) : ''}`}>
          Le catalogue et les prix d'achat sont à jour. Le fichier a été effacé.
        </Banner>
      )}
      {run_.status === 'erreur' && (
        <Banner icon={<XCircle className="size-5 text-destructive" />} title="L'import a échoué" tone="destructive">
          {run_.message}{' '}
          <Link className="font-medium underline" to={`/articles/imports/nouveau?fournisseur=${run_.partner_id}`}>
            Recommencer
          </Link>
        </Banner>
      )}
      {run_.status === 'annule' && (
        <Banner icon={<XCircle className="size-5 text-muted-foreground" />} title="Import annulé">
          Rien n'a été modifié.
        </Banner>
      )}

      {showLines && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {CATEGORIES.map((c) => (
              <button
                key={c.status}
                type="button"
                aria-pressed={active === c.status}
                onClick={() => {
                  setFilter(c.status)
                  setPage(0)
                }}
                className={cn(
                  'rounded-xl border bg-card p-3 text-left shadow-xs transition-colors hover:bg-secondary/50',
                  active === c.status && 'border-primary ring-2 ring-primary/20',
                )}
              >
                <p className={cn('text-2xl font-semibold tabular-nums', c.tone)}>{c.count(run_).toLocaleString('fr-FR')}</p>
                <p className="text-sm font-medium">{c.label}</p>
                <p className="text-xs text-muted-foreground">{c.hint}</p>
              </button>
            ))}
          </div>

          <div className="mt-4 overflow-x-auto rounded-xl border bg-card shadow-xs">
            <table className="w-full text-sm">
              <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Ligne</th>
                  <th className="px-4 py-2.5 font-medium">Référence</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">EAN</th>
                  <th className="px-4 py-2.5 font-medium">Désignation</th>
                  {active === 'erreur' ? (
                    <th className="px-4 py-2.5 font-medium">Problème</th>
                  ) : (
                    <>
                      <th className="px-4 py-2.5 text-right font-medium">{active === 'nouveau' ? 'Prix' : 'Ancien prix'}</th>
                      {active !== 'nouveau' && active !== 'arret' && <th className="px-4 py-2.5 text-right font-medium">Nouveau prix</th>}
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y">
                {lines.data?.items.map((l) => {
                  const change = priceChange(l.old_price, l.new_price)
                  return (
                    <tr key={l.id}>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground tabular-nums">{l.line_no ?? '—'}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{str(l.data.supplier_ref) ?? '—'}</td>
                      <td className="hidden px-4 py-2.5 font-mono text-xs md:table-cell">{str(l.data.ean) ?? '—'}</td>
                      <td className="px-4 py-2.5">
                        {l.article_id ? (
                          <Link to={`/articles/${l.article_id}`} className="hover:underline">
                            {str(l.data.designation) ?? 'Article existant'}
                          </Link>
                        ) : (
                          (str(l.data.designation) ?? <span className="text-muted-foreground">—</span>)
                        )}
                        {active === 'nouveau' && !l.article_id && <Badge variant="success" className="ml-2">article créé</Badge>}
                      </td>
                      {active === 'erreur' ? (
                        <td className="px-4 py-2.5 text-destructive">{l.error}</td>
                      ) : (
                        <>
                          <td className="px-4 py-2.5 text-right tabular-nums">{formatPrice(active === 'nouveau' ? l.new_price : l.old_price)}</td>
                          {active !== 'nouveau' && active !== 'arret' && (
                            <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                              {formatPrice(l.new_price)}
                              {change && (
                                <span className={cn('ml-2 text-xs', change.startsWith('+') ? 'text-destructive' : 'text-emerald-700')}>{change}</span>
                              )}
                            </td>
                          )}
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {lines.data?.total === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune ligne dans cette catégorie.</p>}
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={lines.data?.total ?? 0} noun={['ligne', 'lignes']} onPage={setPage} />
        </>
      )}

      {confirming && <ApplyDialog run={run_} onClose={() => setConfirming(false)} />}
    </>
  )
}

function Banner({ icon, title, children, tone }: { icon: React.ReactNode; title: string; children: React.ReactNode; tone?: 'destructive' }) {
  return (
    <div className={cn('flex gap-3 rounded-xl border bg-card p-4 shadow-xs', tone === 'destructive' && 'border-destructive/40 bg-destructive/5')}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="text-sm">
        <p className="font-medium">{title}</p>
        <p className="text-muted-foreground">{children}</p>
      </div>
    </div>
  )
}

function ApplyDialog({ run, onClose }: { run: ImportRun; onClose: () => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [confirmed, setConfirmed] = useState(false)
  const apply = useMutation({
    mutationFn: () => api<ImportRun>(`/catalog/imports/${run.id}/apply`, { method: 'POST', body: { confirm_discontinue: confirmed } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['import', company?.id, saved.id], saved)
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
      void queryClient.invalidateQueries({ queryKey: ['article-suppliers'] })
      onClose()
    },
  })
  const items = [
    run.new_count && `${run.new_count} nouveaux articles ou références`,
    run.updated_count && `${run.updated_count} prix modifiés`,
    run.reactivated_count && `${run.reactivated_count} articles réactivés`,
    run.discontinued_count && `${run.discontinued_count} articles arrêtés`,
  ].filter(Boolean)
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Appliquer le tarif {run.partner_name} ?</DialogTitle>
          <DialogDescription>Les changements suivants seront enregistrés dans le catalogue de {company?.name} :</DialogDescription>
        </DialogHeader>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {items.length ? items.map((i) => <li key={String(i)}>{i}</li>) : <li>aucun changement</li>}
          {run.error_count > 0 && <li className="text-muted-foreground">{run.error_count} lignes en erreur, ignorées</li>}
        </ul>
        {run.needs_confirmation && (
          <div className="space-y-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p className="flex gap-2 font-medium text-amber-900">
              <AlertTriangle className="size-4 shrink-0" />
              {run.discontinued_count} articles arrêtés sur {run.active_before} : le fichier est-il complet ?
            </p>
            <p className="text-amber-900/80">Un fichier tronqué ou partiel arrêterait à tort une grande partie du catalogue de ce fournisseur.</p>
            <CheckRow checked={confirmed} onChange={setConfirmed} title="Le fichier est complet, je confirme ces arrêts" className="bg-card" />
          </div>
        )}
        <ErrorAlert error={apply.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={apply.isPending || (run.needs_confirmation && !confirmed)} onClick={() => apply.mutate()}>
            {apply.isPending && <LoaderCircle className="animate-spin" />}
            Appliquer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

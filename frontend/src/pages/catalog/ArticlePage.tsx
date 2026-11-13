import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, EllipsisVertical, LoaderCircle, Pencil, Plus, Power, Star, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ErrorAlert } from '@/components/ui/field'
import { api, ApiError } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { ArticleDialog } from '@/pages/catalog/ArticleDialog'
import { SeasonBadge } from '@/pages/catalog/ArticlesPage'
import { EuLabel } from '@/pages/catalog/EuLabel'
import { SupplierLinkDialog } from '@/pages/catalog/SupplierLinkDialog'
import { formatPrice, KINDS, VEHICLE_TYPES, type Article, type ArticleSupplier } from '@/pages/catalog/types'

function Spec({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium">{children ?? '—'}</dd>
    </div>
  )
}

export function ArticlePage() {
  const { id } = useParams()
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'catalog:manage')
  const [editing, setEditing] = useState(false)
  const [linkEdit, setLinkEdit] = useState<ArticleSupplier | 'new' | null>(null)

  const article = useQuery({
    queryKey: ['article', Number(id)],
    queryFn: () => api<Article>(`/catalog/articles/${id}`),
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  })
  const links = useQuery({
    queryKey: ['article-suppliers', company?.id, Number(id)],
    queryFn: () => api<ArticleSupplier[]>(`/catalog/articles/${id}/suppliers`),
  })
  const toggle = useMutation({
    mutationFn: (a: Article) => api<Article>(`/catalog/articles/${a.id}`, { method: 'PATCH', body: { version: a.version, is_active: !a.is_active } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['article', saved.id], saved)
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
  })
  const remove = useMutation({
    mutationFn: (a: Article) => api<void>(`/catalog/articles/${a.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['articles'] })
      navigate('/articles', { replace: true })
    },
  })
  const removeLink = useMutation({
    mutationFn: (l: ArticleSupplier) => api<void>(`/catalog/article-suppliers/${l.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['article-suppliers'] })
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
  })

  const back = (
    <Link to="/articles" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" onClick={(e) => {
      if (window.history.state?.idx > 0) {
        e.preventDefault()
        window.history.back()
      }
    }}>
      <ArrowLeft className="size-4" /> Articles
    </Link>
  )
  if (article.isPending) return <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
  if (article.isError) return <div className="space-y-4">{back}<ErrorAlert error={article.error} /></div>
  const a = article.data
  const t = a.tire
  const flags = t ? [t.reinforced && 'XL', t.runflat && 'Runflat', t.three_pmsf && '3PMSF', t.mud_snow && 'M+S', t.studded && 'Clouté'].filter(Boolean) : []
  const active = links.data?.filter((l) => !l.is_discontinued) ?? []
  const best = active.reduce<string | null>((min, l) => (l.purchase_price !== null && (min === null || Number(l.purchase_price) < Number(min)) ? l.purchase_price : min), null)

  return (
    <>
      {back}
      <div className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {a.designation}
            {!a.is_active && <Badge variant="outline">Désactivé</Badge>}
          </h1>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono">{a.code}</span> · {KINDS[a.kind]}
            {a.brand && ` · ${a.brand.name}`}
            {a.ean && (
              <>
                {' · EAN '}
                <span className="font-mono">{a.ean}</span>
              </>
            )}
          </p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Modifier
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" aria-label="Actions">
                  <EllipsisVertical />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => toggle.mutate(a)}>
                  <Power /> {a.is_active ? 'Désactiver' : 'Réactiver'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onSelect={() => window.confirm(`Supprimer définitivement ${a.code} ?`) && remove.mutate(a)}
                >
                  <Trash2 /> Supprimer
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
      <ErrorAlert error={toggle.error ?? remove.error} />

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="rounded-xl border bg-card p-5 shadow-xs">
          <h2 className="mb-4 text-sm font-semibold">Caractéristiques</h2>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {t ? (
              <>
                <Spec label="Dimension">{t.size && <span className="font-mono">{t.size}</span>}</Spec>
                <Spec label="Véhicule">{VEHICLE_TYPES[t.vehicle_type]}</Spec>
                <Spec label="Saison"><SeasonBadge season={t.season} /></Spec>
                <Spec label="Particularités">{flags.length ? flags.join(' · ') : null}</Spec>
                <Spec label="Étiquette UE"><EuLabel fuel={t.fuel_class} wet={t.wet_class} noise={t.noise_db} /></Spec>
                <Spec label="N° EPREL">{t.eprel_id && <span className="font-mono">{t.eprel_id}</span>}</Spec>
              </>
            ) : (
              <Spec label="Catégorie">{a.category}</Spec>
            )}
            <Spec label="Référence fabricant">{a.manufacturer_ref && <span className="font-mono">{a.manufacturer_ref}</span>}</Spec>
            <Spec label="Unité">{a.unit}</Spec>
            <Spec label="Modifié le">{formatDateTime(a.updated_at)}</Spec>
          </dl>
        </section>
        <section className="rounded-xl border bg-card p-5 shadow-xs">
          <h2 className="text-sm font-semibold">Meilleur prix d'achat</h2>
          <p className="mt-2 text-3xl font-semibold tabular-nums">{formatPrice(best)}</p>
          <p className="text-sm text-muted-foreground">
            {active.length} fournisseur{active.length > 1 ? 's' : ''} actif{active.length > 1 ? 's' : ''} dans {company?.name}
          </p>
        </section>
      </div>

      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Fournisseurs</h2>
          {canManage && (
            <Button size="sm" onClick={() => setLinkEdit('new')}>
              <Plus /> Ajouter un fournisseur
            </Button>
          )}
        </div>
        <ErrorAlert error={links.error ?? removeLink.error} />
        <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
          <table className="w-full text-sm">
            <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Fournisseur</th>
                <th className="px-4 py-2.5 font-medium">Référence</th>
                <th className="px-4 py-2.5 text-right font-medium">Prix d'achat HT</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Prix mis à jour</th>
                <th className="px-4 py-2.5 font-medium">Statut</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {links.data?.map((l) => (
                <tr key={l.id} className={l.is_discontinued ? 'opacity-60' : undefined}>
                  <td className="px-4 py-3">
                    <Link to={`/fournisseurs/${l.partner.id}`} className="font-medium hover:underline">
                      {l.partner.name}
                    </Link>
                    {l.is_preferred && (
                      <Badge variant="accent" className="ml-2">
                        <Star /> Préféré
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{l.supplier_ref ?? '—'}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">{formatPrice(l.purchase_price)}</td>
                  <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{l.price_updated_at ? formatDateTime(l.price_updated_at) : '—'}</td>
                  <td className="px-4 py-3">
                    {l.is_discontinued ? <Badge variant="outline">Arrêté</Badge> : <Badge variant="success">Actif</Badge>}
                  </td>
                  <td className="px-4 py-3">
                    {canManage && (
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" title="Modifier" aria-label={`Modifier ${l.partner.name}`} onClick={() => setLinkEdit(l)}>
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          title="Retirer"
                          aria-label={`Retirer ${l.partner.name}`}
                          onClick={() => window.confirm(`Retirer ${l.partner.name} des fournisseurs de cet article ?`) && removeLink.mutate(l)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {links.data?.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">Aucun fournisseur dans cette société.</p>}
        </div>
      </section>

      {editing && <ArticleDialog article={a} onClose={() => setEditing(false)} />}
      {linkEdit && (
        <SupplierLinkDialog
          articleId={a.id}
          link={linkEdit === 'new' ? null : linkEdit}
          excluded={links.data?.map((l) => l.partner.id) ?? []}
          onClose={() => setLinkEdit(null)}
        />
      )}
    </>
  )
}

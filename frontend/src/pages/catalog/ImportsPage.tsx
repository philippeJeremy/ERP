import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FileSpreadsheet, History, LoaderCircle, Plus, RadioTower } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { SourcesTab } from '@/pages/catalog/SourcesTab'
import { RUN_STATUSES, type ImportRun, type Page } from '@/pages/catalog/types'

const PAGE_SIZE = 20

export function ImportsPage() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  const [params, update] = useUrlState()
  const tab = params.get('onglet') === 'releves' ? 'releves' : 'historique'
  const allowed = can(me?.permissions, 'catalog:import')
  const runs = useQuery({
    queryKey: ['imports', company?.id, page],
    queryFn: () => api<Page<ImportRun>>(`/catalog/imports?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`),
    enabled: allowed,
    // Tant qu'un import est en cours, on rafraîchit la liste.
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === 'analyse' || r.status === 'application') ? 2000 : false),
  })
  if (!allowed) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit d'importer des tarifs.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <Link to="/articles" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Articles
      </Link>
      <div className="mt-3">
        <PageHeader
          title="Imports tarifs"
          description="Les fichiers tarifs des fournisseurs, déposés à la main ou relevés automatiquement par FTP/SFTP : analysés, vérifiés, puis appliqués au catalogue."
          actions={
            <Button asChild>
              <Link to="/articles/imports/nouveau">
                <Plus /> Nouvel import
              </Link>
            </Button>
          }
        />
      </div>
      <div role="tablist" className="mb-4 flex gap-1 border-b">
        {[
          { id: 'historique', label: 'Historique', icon: History },
          { id: 'releves', label: 'Relèves automatiques', icon: RadioTower },
        ].map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => update({ onglet: t.id === 'historique' ? null : t.id })}
            className={cn(
              '-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <t.icon className="size-4" />
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'releves' ? (
        <SourcesTab />
      ) : (
        <>
      <ErrorAlert error={runs.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="px-4 py-2.5 font-medium">Fournisseur</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Fichier</th>
              <th className="px-4 py-2.5 font-medium">Résultat</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {runs.data?.items.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/articles/imports/${r.id}`)}>
                <td className="px-4 py-3 whitespace-nowrap">{formatDateTime(r.created_at)}</td>
                <td className="px-4 py-3">
                  <p className="font-medium">{r.partner_name}</p>
                  {r.source !== 'manuel' && <p className="text-xs text-muted-foreground">relève {r.source.toUpperCase()}</p>}
                </td>
                <td className="hidden px-4 py-3 md:table-cell">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <FileSpreadsheet className="size-4 shrink-0" /> <span className="truncate">{r.filename}</span>
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {r.status === 'analyse' ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : r.status === 'annule' || (r.status === 'erreur' && !r.total_lines) ? (
                    '—'
                  ) : (
                    [
                      r.new_count && `${r.new_count} nouveaux`,
                      r.updated_count && `${r.updated_count} prix modifiés`,
                      r.discontinued_count && `${r.discontinued_count} arrêtés`,
                      r.error_count && `${r.error_count} erreurs`,
                    ]
                      .filter(Boolean)
                      .join(' · ') || 'Aucun changement'
                  )}
                </td>
                <td className="px-4 py-3">
                  <Badge variant={RUN_STATUSES[r.status].variant}>{RUN_STATUSES[r.status].label}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <FileSpreadsheet className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun import pour le moment</p>
            <p className="text-sm text-muted-foreground">Déposez le fichier tarif d'un fournisseur pour remplir le catalogue.</p>
          </div>
        )}
        {runs.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={runs.data?.total ?? 0} noun={['import', 'imports']} onPage={setPage} />
        </>
      )}
    </>
  )
}

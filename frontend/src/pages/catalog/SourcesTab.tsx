import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleSlash, Clock, LoaderCircle, Pencil, Play, Plus, RadioTower, ShieldAlert, Trash2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { SourceDialog } from '@/pages/catalog/SourceDialog'
import { INTERVALS, PROTOCOLS, type ImportSource } from '@/pages/catalog/types'

function LastResult({ s }: { s: ImportSource }) {
  if (!s.last_check_at) return <span className="text-muted-foreground">Pas encore relevé</span>
  const Icon = s.last_status === 'ok' ? CheckCircle2 : s.last_status === 'erreur' ? XCircle : CircleSlash
  const tone = s.last_status === 'ok' ? 'text-emerald-600' : s.last_status === 'erreur' ? 'text-destructive' : 'text-muted-foreground'
  return (
    <div className="flex gap-2">
      <Icon className={`mt-0.5 size-4 shrink-0 ${tone}`} />
      <div className="min-w-0">
        <p title={formatDateTime(s.last_check_at)}>{formatRelative(s.last_check_at)}</p>
        <p className="text-xs text-muted-foreground">
          {s.last_message}
          {s.last_run_id && (
            <>
              {' · '}
              <Link className="text-primary hover:underline" to={`/articles/imports/${s.last_run_id}`}>
                voir l'import
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  )
}

/** Onglet « Relèves automatiques » de la page Imports tarifs. */
export function SourcesTab() {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<ImportSource | 'new' | null>(null)
  const settings = useQuery({
    queryKey: ['import-sources-settings'],
    queryFn: () => api<{ secrets_configured: boolean }>('/catalog/import-sources/settings'),
  })
  // Rafraîchi régulièrement : les relèves tournent dans le worker, en arrière-plan.
  const sources = useQuery({
    queryKey: ['import-sources', company?.id],
    queryFn: () => api<ImportSource[]>('/catalog/import-sources'),
    refetchInterval: 5000,
  })
  const runNow = useMutation({
    mutationFn: (s: ImportSource) => api<ImportSource>(`/catalog/import-sources/${s.id}/run`, { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['import-sources'] })
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })
  const remove = useMutation({
    mutationFn: (s: ImportSource) => api<void>(`/catalog/import-sources/${s.id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['import-sources'] }),
  })
  const noKey = settings.data && !settings.data.secrets_configured

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          L'ERP va chercher lui-même le fichier tarif sur le serveur FTP ou SFTP du fournisseur, à la fréquence choisie, et ne
          prend que les nouveaux fichiers. Les fichiers du fournisseur ne sont jamais modifiés.
        </p>
        <Button disabled={!!noKey} onClick={() => setEditing('new')}>
          <Plus /> Nouvelle relève
        </Button>
      </div>
      {noKey && (
        <div className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-900">
          <ShieldAlert className="size-5 shrink-0" />
          <p>
            Le serveur n'a pas de clé de chiffrement (<code>SECRETS_KEY</code> dans son <code>.env</code>) : impossible d'enregistrer
            les mots de passe des fournisseurs. Un administrateur doit la générer et redémarrer l'application.
          </p>
        </div>
      )}
      <ErrorAlert error={sources.error ?? runNow.error ?? remove.error} />

      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Fournisseur</th>
              <th className="px-4 py-2.5 font-medium">Serveur</th>
              <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Fréquence</th>
              <th className="px-4 py-2.5 font-medium">Dernière relève</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {sources.data?.map((s) => (
              <tr key={s.id} className={s.is_active ? undefined : 'opacity-60'}>
                <td className="px-4 py-3 align-top">
                  <p className="font-medium">{s.partner_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.name} · format {s.profile_name ?? <span className="text-destructive">supprimé</span>}
                  </p>
                </td>
                <td className="px-4 py-3 align-top">
                  <p className="flex items-center gap-2">
                    <Badge variant={s.protocol === 'ftp' ? 'destructive' : 'secondary'}>{PROTOCOLS[s.protocol].label}</Badge>
                    <span className="font-mono text-xs">{s.host}</span>
                  </p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {s.remote_dir.replace(/\/$/, '')}/{s.pattern}
                  </p>
                </td>
                <td className="hidden px-4 py-3 align-top lg:table-cell">
                  <p>{INTERVALS[s.interval_hours] ?? `Toutes les ${s.interval_hours} h`}</p>
                  <p className="text-xs text-muted-foreground">
                    {!s.is_active ? (
                      'Désactivée'
                    ) : s.next_check_at ? (
                      <span className="inline-flex items-center gap-1">
                        <Clock className="size-3" /> prochaine {formatRelative(s.next_check_at)}
                      </span>
                    ) : null}
                  </p>
                  {s.auto_apply && <Badge variant="accent" className="mt-1">application auto</Badge>}
                </td>
                <td className="max-w-md px-4 py-3 align-top">
                  <LastResult s={s} />
                </td>
                <td className="px-4 py-3 align-top">
                  <div className="flex justify-end gap-1">
                    <Button variant="outline" size="sm" disabled={runNow.isPending} onClick={() => runNow.mutate(s)} title="Relever maintenant">
                      {runNow.isPending && runNow.variables?.id === s.id ? <LoaderCircle className="animate-spin" /> : <Play />}
                      Relever
                    </Button>
                    <Button variant="ghost" size="icon" aria-label={`Modifier la relève ${s.partner_name}`} onClick={() => setEditing(s)}>
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      aria-label={`Supprimer la relève ${s.partner_name}`}
                      onClick={() => window.confirm(`Supprimer la relève « ${s.name} » de ${s.partner_name} ?`) && remove.mutate(s)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sources.data?.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <RadioTower className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucune relève automatique</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Demandez à votre fournisseur un accès SFTP (ou FTPS) à son fichier tarif, puis créez la relève. Il faut d'abord un import
              manuel de ce fournisseur, pour mémoriser le format des colonnes.
            </p>
          </div>
        )}
        {sources.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      {editing && <SourceDialog source={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

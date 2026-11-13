import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FileSpreadsheet, KeyRound, LoaderCircle, PlugZap, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { formatSize, INTERVALS, PROTOCOLS, type ConnectionTest, type ImportProfile, type ImportSource, type Protocol } from '@/pages/catalog/types'
import type { PartnerPage } from '@/pages/partners/types'

interface Form {
  partner_id: string
  profile_id: string
  name: string
  protocol: Protocol
  host: string
  port: string
  username: string
  auth_method: 'password' | 'key'
  secret: string
  tls_verify: boolean
  remote_dir: string
  pattern: string
  interval_hours: number
  auto_apply: boolean
  is_active: boolean
}

/** Créer ou modifier une relève, avec test de connexion obligatoire en SFTP. */
export function SourceDialog({ source, onClose }: { source: ImportSource | null; onClose: () => void }) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Form>({
    partner_id: source ? String(source.partner_id) : '',
    profile_id: source?.profile_id ? String(source.profile_id) : '',
    name: source?.name ?? 'Relève',
    protocol: source?.protocol ?? 'sftp',
    host: source?.host ?? '',
    port: source ? String(source.port) : '',
    username: source?.username ?? '',
    auth_method: source?.auth_method ?? 'password',
    secret: '',
    tls_verify: source?.tls_verify ?? true,
    remote_dir: source?.remote_dir ?? '/',
    pattern: source?.pattern ?? '*.csv',
    interval_hours: source?.interval_hours ?? 24,
    auto_apply: source?.auto_apply ?? false,
    is_active: source?.is_active ?? true,
  })
  // Empreinte SFTP : celle enregistrée, ou celle lue au test et confirmée par l'utilisateur.
  const [test, setTest] = useState<ConnectionTest | null>(null)
  const [keyConfirmed, setKeyConfirmed] = useState(false)
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    // Changer de serveur invalide le test (et donc l'empreinte lue).
    if (['protocol', 'host', 'port'].includes(key)) {
      setTest(null)
      setKeyConfirmed(false)
    }
  }

  const suppliers = useQuery({
    queryKey: ['partners', company?.id, 'supplier-options'],
    queryFn: () => api<PartnerPage>('/partners?role=supplier&active=true&limit=200&sort=name'),
  })
  const profiles = useQuery({
    queryKey: ['import-profiles', company?.id, form.partner_id],
    queryFn: () => api<ImportProfile[]>(`/catalog/import-profiles?partner_id=${form.partner_id}`),
    enabled: !!form.partner_id,
  })
  const profileId = form.profile_id || (profiles.data?.[0] ? String(profiles.data[0].id) : '')

  const connection = () => ({
    protocol: form.protocol,
    host: form.host.trim(),
    port: form.port ? Number(form.port) : null,
    username: form.username.trim(),
    auth_method: form.protocol === 'sftp' ? form.auth_method : 'password',
    secret: form.secret || null,
    tls_verify: form.tls_verify,
    remote_dir: form.remote_dir.trim() || '/',
    pattern: form.pattern.trim() || '*',
  })
  const runTest = useMutation({
    mutationFn: () => api<ConnectionTest>('/catalog/import-sources/test', { method: 'POST', body: { ...connection(), source_id: source?.id ?? null } }),
    onMutate: () => {
      setTest(null)
      setKeyConfirmed(false)
    },
    onSuccess: setTest,
  })

  const sameServer = source && source.protocol === form.protocol && source.host === form.host.trim() && String(source.port) === (form.port || String(PROTOCOLS[form.protocol].port))
  const storedKeyOk = !!(sameServer && source?.host_key && (!test || test.host_key === source.host_key))
  const hostKey = form.protocol !== 'sftp' ? null : storedKeyOk ? source!.host_key : keyConfirmed && test ? test.host_key : null
  const missing = [
    !form.partner_id && 'le fournisseur',
    !profileId && 'le format',
    !form.host.trim() && 'le serveur',
    !form.username.trim() && "l'identifiant",
    !form.secret && !source?.has_secret && (form.auth_method === 'key' && form.protocol === 'sftp' ? 'la clé SSH' : 'le mot de passe'),
    form.protocol === 'sftp' && !hostKey && "l'empreinte du serveur (testez la connexion)",
  ].filter(Boolean)

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...connection(),
        host_key: hostKey,
        partner_id: Number(form.partner_id),
        profile_id: Number(profileId),
        name: form.name.trim() || 'Relève',
        interval_hours: form.interval_hours,
        auto_apply: form.auto_apply,
        is_active: form.is_active,
      }
      return source
        ? api<ImportSource>(`/catalog/import-sources/${source.id}`, { method: 'PUT', body })
        : api<ImportSource>('/catalog/import-sources', { method: 'POST', body })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['import-sources'] })
      onClose()
    },
  })

  const input = (key: 'name' | 'host' | 'port' | 'username' | 'remote_dir' | 'pattern', label: string, extra?: { placeholder?: string; hint?: string; mono?: boolean; className?: string }) => (
    <div className={extra?.className}>
      <Field id={`src_${key}`} label={label} hint={extra?.hint}>
        <Input
          id={`src_${key}`}
          autoComplete="off"
          spellCheck={false}
          placeholder={extra?.placeholder}
          className={extra?.mono ? 'font-mono' : undefined}
          value={form[key]}
          onChange={(e) => set(key, e.target.value)}
        />
      </Field>
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{source ? `Relève ${source.partner_name}` : 'Nouvelle relève automatique'}</DialogTitle>
          <DialogDescription>L'ERP va chercher le fichier tarif sur le serveur du fournisseur et l'analyse comme un import manuel.</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field id="src_partner" label="Fournisseur">
              <NativeSelect id="src_partner" value={form.partner_id} disabled={!!source} onChange={(e) => setForm((f) => ({ ...f, partner_id: e.target.value, profile_id: '' }))}>
                <option value="">— Choisir —</option>
                {suppliers.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="src_profile" label="Format des colonnes">
              <NativeSelect id="src_profile" value={profileId} disabled={!profiles.data?.length} onChange={(e) => set('profile_id', e.target.value)}>
                {!profiles.data?.length && <option value="">—</option>}
                {profiles.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.file_format === 'csv' ? 'CSV' : 'Excel'})
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {input('name', 'Nom de la relève')}
          </div>
          {form.partner_id && profiles.data?.length === 0 && (
            <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">
              Ce fournisseur n'a pas encore de format d'import. Faites d'abord un{' '}
              <Link className="font-medium underline" to={`/articles/imports/nouveau?fournisseur=${form.partner_id}`}>
                import manuel
              </Link>{' '}
              d'un de ses fichiers : la correspondance des colonnes sera mémorisée et réutilisée ici.
            </p>
          )}

          <fieldset>
            <legend className="mb-2 text-sm font-medium">Protocole</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {(Object.keys(PROTOCOLS) as Protocol[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={form.protocol === p}
                  onClick={() => set('protocol', p)}
                  className={cn('rounded-lg border p-3 text-left text-sm transition-colors', form.protocol === p ? 'border-primary bg-secondary ring-2 ring-primary/20' : 'hover:bg-secondary/50')}
                >
                  <span className="flex items-center gap-2 font-medium">
                    {PROTOCOLS[p].label}
                    {p === 'sftp' && <Badge variant="success">recommandé</Badge>}
                    {p === 'ftp' && <Badge variant="destructive">non chiffré</Badge>}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">{PROTOCOLS[p].hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-6">
            {input('host', 'Serveur', { placeholder: 'sftp.fournisseur.fr', mono: true, className: 'sm:col-span-4' })}
            {input('port', 'Port', { placeholder: String(PROTOCOLS[form.protocol].port), className: 'sm:col-span-2' })}
            {input('username', 'Identifiant', { className: 'sm:col-span-3' })}
            {form.protocol === 'sftp' ? (
              <div className="sm:col-span-3">
                <Field id="src_auth" label="Authentification">
                  <NativeSelect id="src_auth" value={form.auth_method} onChange={(e) => set('auth_method', e.target.value as Form['auth_method'])}>
                    <option value="password">Mot de passe</option>
                    <option value="key">Clé SSH</option>
                  </NativeSelect>
                </Field>
              </div>
            ) : (
              <div className="sm:col-span-3" />
            )}
            <div className="sm:col-span-6">
              {form.protocol === 'sftp' && form.auth_method === 'key' ? (
                <Field id="src_secret" label="Clé privée SSH" hint={source?.has_secret ? 'Laisser vide pour garder la clé enregistrée' : 'Format OpenSSH ou PEM, sans phrase de passe. Donnez au fournisseur la clé PUBLIQUE correspondante.'}>
                  <Textarea id="src_secret" rows={4} className="font-mono text-xs" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" value={form.secret} onChange={(e) => set('secret', e.target.value)} />
                </Field>
              ) : (
                <Field id="src_secret" label="Mot de passe" hint={source?.has_secret ? 'Laisser vide pour garder le mot de passe enregistré' : 'Chiffré avant d’être enregistré, jamais réaffiché.'}>
                  <Input id="src_secret" type="password" autoComplete="new-password" placeholder={source?.has_secret ? '•••••••• (inchangé)' : ''} value={form.secret} onChange={(e) => set('secret', e.target.value)} />
                </Field>
              )}
            </div>
            {input('remote_dir', 'Dossier', { mono: true, className: 'sm:col-span-3', placeholder: '/tarifs' })}
            {input('pattern', 'Nom du fichier', { mono: true, className: 'sm:col-span-3', hint: '* = n’importe quels caractères : tarif_*.csv' })}
          </div>
          {form.protocol === 'ftps' && (
            <CheckRow
              checked={form.tls_verify}
              onChange={(on) => set('tls_verify', on)}
              title="Vérifier le certificat du serveur"
              description="À ne décocher que si le fournisseur utilise un certificat auto-signé (la connexion reste chiffrée, mais l'identité du serveur n'est plus garantie)."
            />
          )}

          {/* Test de connexion */}
          <div className="rounded-lg border bg-secondary/30 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                {form.protocol === 'sftp' ? 'Obligatoire en SFTP : vérifie les accès et lit l’empreinte du serveur.' : 'Vérifie les accès et liste les fichiers trouvés.'}
              </p>
              <Button type="button" variant="outline" disabled={!form.host || !form.username || runTest.isPending} onClick={() => runTest.mutate()}>
                {runTest.isPending ? <LoaderCircle className="animate-spin" /> : <PlugZap />}
                Tester la connexion
              </Button>
            </div>
            <ErrorAlert error={runTest.error} />
            {test && (
              <div className="mt-3 space-y-3">
                {test.host_key && (
                  <div className={cn('rounded-md border bg-card p-3 text-sm', test.host_key_changed && 'border-destructive/50')}>
                    <p className="flex items-center gap-2 font-medium">
                      {test.host_key_changed ? <ShieldAlert className="size-4 text-destructive" /> : <KeyRound className="size-4" />}
                      {test.host_key_changed ? "L'empreinte du serveur a CHANGÉ" : 'Empreinte du serveur'}
                    </p>
                    <p className="mt-1 font-mono text-xs break-all">{test.host_key}</p>
                    {storedKeyOk ? (
                      <p className="mt-2 flex items-center gap-1 text-emerald-700">
                        <CheckCircle2 className="size-4" /> Identique à l'empreinte confirmée.
                      </p>
                    ) : (
                      <CheckRow
                        className="mt-2"
                        checked={keyConfirmed}
                        onChange={setKeyConfirmed}
                        title="J'ai vérifié cette empreinte auprès du fournisseur"
                        description={
                          test.host_key_changed
                            ? 'Un changement peut venir d’un nouveau serveur… ou d’un imposteur. Confirmez avec le fournisseur avant d’accepter.'
                            : 'Elle garantit, à chaque relève, qu’on parle bien au serveur du fournisseur (et pas à un imposteur qui recevrait le mot de passe).'
                        }
                      />
                    )}
                  </div>
                )}
                <div>
                  <p className="mb-1 text-sm font-medium">
                    {test.files.length ? `${test.files.length} fichier(s) « ${form.pattern} » trouvé(s)` : `Connexion réussie, mais aucun fichier « ${form.pattern} » dans ${form.remote_dir}`}
                  </p>
                  {test.files.length > 0 && (
                    <ul className="divide-y rounded-md border bg-card text-sm">
                      {test.files.slice(0, 6).map((f, i) => (
                        <li key={f.name} className="flex items-center gap-2 px-3 py-1.5">
                          <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                          <span className="truncate font-mono text-xs">{f.name}</span>
                          {i === 0 && !f.already_seen && <Badge variant="accent">sera importé</Badge>}
                          {f.already_seen && <Badge variant="outline">déjà traité</Badge>}
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                            {formatSize(f.size)}
                            {f.mtime && ` · ${formatDateTime(f.mtime)}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field id="src_interval" label="Fréquence">
              <NativeSelect id="src_interval" value={form.interval_hours} onChange={(e) => set('interval_hours', Number(e.target.value))}>
                {Object.entries(INTERVALS).map(([h, l]) => (
                  <option key={h} value={h}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <CheckRow
              className="sm:col-span-2"
              checked={form.auto_apply}
              onChange={(on) => set('auto_apply', on)}
              title="Appliquer automatiquement"
              description="Si l'analyse est propre (moins de 5 % d'erreurs, pas d'arrêts massifs). Sinon l'import attend votre validation."
            />
          </div>
          {source && <CheckRow checked={form.is_active} onChange={(on) => set('is_active', on)} title="Relève active" description="Décochée : plus aucune relève planifiée (« Relever maintenant » reste possible)." />}
        </div>

        <ErrorAlert error={save.error} />
        <DialogFooter className="items-center">
          {missing.length > 0 && (
            <span className="mr-auto flex items-center gap-1 text-xs text-muted-foreground">
              <AlertTriangle className="size-3.5" /> Manque : {missing.join(', ')}
            </span>
          )}
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={missing.length > 0 || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

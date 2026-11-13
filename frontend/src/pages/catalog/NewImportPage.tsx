import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, FileSpreadsheet, LoaderCircle, Settings2, Upload } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { formatSize, KINDS, VEHICLE_TYPES, type FilePreview, type ImportProfile, type ImportRun, type Kind } from '@/pages/catalog/types'
import type { PartnerPage } from '@/pages/partners/types'

const ACCEPT = '.csv,.txt,.xlsx,.xls'
// Champs regroupés pour l'écran de correspondance.
const FIELD_GROUPS: { title: string; fields: string[] }[] = [
  { title: 'Identification et prix', fields: ['supplier_ref', 'ean', 'purchase_price', 'designation', 'brand', 'manufacturer_ref', 'kind', 'category'] },
  { title: 'Pneus (facultatif : extraits de la désignation sinon)', fields: ['vehicle_type', 'season', 'width', 'aspect_ratio', 'rim', 'load_index', 'speed_index'] },
  { title: 'Étiquette européenne', fields: ['fuel_class', 'wet_class', 'noise_db', 'noise_class', 'eprel_id'] },
]

interface Settings {
  header_row: number
  sheet_name: string
  delimiter: string
  encoding: string
}

function Step({ n, title, active, done }: { n: number; title: string; active: boolean; done: boolean }) {
  return (
    <li className={cn('flex items-center gap-2 text-sm', active ? 'font-medium text-foreground' : 'text-muted-foreground')}>
      <span className={cn('flex size-6 items-center justify-center rounded-full border text-xs', active && 'border-primary bg-primary text-primary-foreground', done && 'border-emerald-600 bg-emerald-600 text-white')}>
        {done ? <Check className="size-3.5" /> : n}
      </span>
      {title}
    </li>
  )
}

export function NewImportPage() {
  const { company } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const [partnerId, setPartnerId] = useState(params.get('fournisseur') ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [choice, setProfileChoice] = useState<string>('') // id, ou 'new'
  const [step, setStep] = useState<'fichier' | 'colonnes'>('fichier')
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const suppliers = useQuery({
    queryKey: ['partners', company?.id, 'supplier-options'],
    queryFn: () => api<PartnerPage>('/partners?role=supplier&active=true&limit=200&sort=name'),
  })
  const profiles = useQuery({
    queryKey: ['import-profiles', company?.id, partnerId],
    queryFn: () => api<ImportProfile[]>(`/catalog/import-profiles?partner_id=${partnerId}`),
    enabled: !!partnerId,
  })
  // Par défaut (calculé à l'affichage) : le format déjà enregistré pour ce fournisseur,
  // sinon un nouveau.
  const list = profiles.data
  const profileChoice = !list
    ? ''
    : choice === 'new' || list.some((p) => String(p.id) === choice)
      ? choice
      : list[0]
        ? String(list[0].id)
        : 'new'
  const profile = profiles.data?.find((p) => String(p.id) === profileChoice) ?? null

  const upload = useMutation({
    mutationFn: (profileId: number) => {
      const form = new FormData()
      form.append('profile_id', String(profileId))
      form.append('file', file!)
      return api<ImportRun>('/catalog/imports', { method: 'POST', body: form })
    },
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
      navigate(`/articles/imports/${run.id}`)
    },
  })

  const pickFile = (f: File | undefined) => {
    if (f) setFile(f)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pickFile(e.dataTransfer.files[0])
  }
  const ready = !!partnerId && !!file && !!profileChoice

  return (
    <>
      <Link to="/articles/imports" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Imports tarifs
      </Link>
      <div className="mt-3">
        <PageHeader title="Nouvel import de tarif" description="Rien n'est modifié avant que vous ayez vu et validé le résultat de l'analyse." />
      </div>
      <ol className="mb-6 flex flex-wrap gap-6">
        <Step n={1} title="Fournisseur et fichier" active={step === 'fichier'} done={step === 'colonnes'} />
        <Step n={2} title="Correspondance des colonnes" active={step === 'colonnes'} done={false} />
        <Step n={3} title="Aperçu et validation" active={false} done={false} />
      </ol>

      {step === 'fichier' ? (
        <div className="max-w-3xl space-y-6 rounded-xl border bg-card p-6 shadow-xs">
          <Field id="imp_partner" label="Fournisseur">
            <NativeSelect id="imp_partner" value={partnerId} onChange={(e) => setPartnerId(e.target.value)}>
              <option value="">{suppliers.isPending ? 'Chargement…' : '— Choisir —'}</option>
              {suppliers.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.code})
                </option>
              ))}
            </NativeSelect>
          </Field>

          <div>
            <p className="mb-2 text-sm font-medium">Fichier tarif</p>
            <button
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                'flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-sm transition-colors',
                dragging ? 'border-primary bg-secondary' : 'hover:bg-secondary/50',
              )}
            >
              {file ? (
                <>
                  <FileSpreadsheet className="size-8 text-primary" />
                  <span className="font-medium">{file.name}</span>
                  <span className="text-muted-foreground">{formatSize(file.size)} · cliquez pour changer</span>
                </>
              ) : (
                <>
                  <Upload className="size-8 text-muted-foreground" />
                  <span className="font-medium">Déposez le fichier ici, ou cliquez pour le choisir</span>
                  <span className="text-muted-foreground">CSV, TXT, Excel (.xlsx, .xls) — 20 Mo maximum</span>
                </>
              )}
            </button>
            <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label="Fichier tarif" onChange={(e) => pickFile(e.target.files?.[0])} />
          </div>

          {partnerId && profiles.data && (
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">Format du fichier</legend>
              {profiles.data.map((p) => (
                <CheckRow
                  key={p.id}
                  checked={profileChoice === String(p.id)}
                  onChange={() => setProfileChoice(String(p.id))}
                  title={
                    <span className="flex items-center gap-2">
                      {p.name} <Badge variant="secondary">{p.file_format === 'csv' ? 'CSV' : 'Excel'}</Badge>
                      {p.full_catalog && <Badge variant="outline">fichier complet</Badge>}
                    </span>
                  }
                  description={`${Object.keys(p.mapping).length} colonnes reconnues · modifié le ${formatDateTime(p.updated_at)}`}
                />
              ))}
              <CheckRow
                checked={profileChoice === 'new'}
                onChange={() => setProfileChoice('new')}
                title="Nouveau format de fichier"
                description={profiles.data.length ? 'Le fournisseur a changé de format, ou envoie un autre fichier.' : "Premier import de ce fournisseur : vous indiquerez à quoi correspond chaque colonne (une seule fois, c'est mémorisé)."}
              />
            </fieldset>
          )}

          <ErrorAlert error={upload.error} />
          <div className="flex flex-wrap justify-end gap-2">
            {profile && (
              <Button variant="outline" disabled={!ready} onClick={() => setStep('colonnes')}>
                <Settings2 /> Modifier le format
              </Button>
            )}
            {profile ? (
              <Button disabled={!ready || upload.isPending} onClick={() => upload.mutate(profile.id)}>
                {upload.isPending && <LoaderCircle className="animate-spin" />}
                Analyser le fichier
              </Button>
            ) : (
              <Button disabled={!ready} onClick={() => setStep('colonnes')}>
                Continuer
              </Button>
            )}
          </div>
        </div>
      ) : (
        <MappingStep
          file={file!}
          partnerId={Number(partnerId)}
          profile={profile}
          onBack={() => setStep('fichier')}
          onSaved={(p) => upload.mutate(p.id)}
          uploading={upload.isPending}
          uploadError={upload.error}
        />
      )}
    </>
  )
}

function MappingStep({
  file,
  partnerId,
  profile,
  onBack,
  onSaved,
  uploading,
  uploadError,
}: {
  file: File
  partnerId: number
  profile: ImportProfile | null
  onBack: () => void
  onSaved: (p: ImportProfile) => void
  uploading: boolean
  uploadError: unknown
}) {
  const queryClient = useQueryClient()
  const [settings, setSettings] = useState<Settings>({
    header_row: profile?.header_row ?? 1,
    sheet_name: profile?.sheet_name ?? '',
    delimiter: profile?.delimiter ?? '',
    encoding: profile?.encoding ?? '',
  })
  const [mapping, setMapping] = useState<Record<string, string> | null>(profile ? { ...profile.mapping } : null)
  const [options, setOptions] = useState({
    name: profile?.name ?? 'Tarif',
    full_catalog: profile?.full_catalog ?? true,
    default_kind: (profile?.default_kind ?? 'pneu') as Kind,
    default_vehicle_type: profile?.default_vehicle_type ?? '',
    parse_designation: profile?.parse_designation ?? true,
  })

  const preview = useQuery({
    queryKey: ['import-preview', file.name, file.size, file.lastModified, settings],
    queryFn: () => {
      const form = new FormData()
      form.append('file', file)
      form.append('header_row', String(settings.header_row))
      if (settings.sheet_name) form.append('sheet_name', settings.sheet_name)
      if (settings.delimiter) form.append('delimiter', settings.delimiter)
      if (settings.encoding) form.append('encoding', settings.encoding)
      return api<FilePreview>('/catalog/imports/preview', { method: 'POST', body: form })
    },
    retry: false,
  })
  const data = preview.data
  const headers = data?.headers ?? []
  // Nouveau format : tant que rien n'est modifié, on affiche la proposition automatique.
  const base = mapping ?? data?.suggested_mapping ?? {}
  // Une colonne qui n'existe plus dans ce fichier (le fournisseur a changé de format).
  const current = Object.fromEntries(Object.entries(base).filter(([, h]) => headers.includes(h)))
  const lost = Object.entries(base).filter(([, h]) => data && !headers.includes(h))
  const mappedHeaders = new Set(Object.values(current))
  const missing = [!current.purchase_price && "le prix d'achat", !current.ean && !current.supplier_ref && 'le code EAN ou la référence fournisseur'].filter(Boolean)

  const save = useMutation({
    mutationFn: () => {
      const body = {
        partner_id: partnerId,
        name: options.name,
        file_format: data!.file_format,
        delimiter: data!.file_format === 'csv' ? settings.delimiter || data!.delimiter : null,
        encoding: data!.file_format === 'csv' ? settings.encoding || data!.encoding : null,
        sheet_name: data!.file_format === 'excel' ? settings.sheet_name || null : null,
        header_row: settings.header_row,
        mapping: current,
        full_catalog: options.full_catalog,
        default_kind: options.default_kind,
        default_vehicle_type: options.default_vehicle_type || null,
        parse_designation: options.parse_designation,
      }
      return profile
        ? api<ImportProfile>(`/catalog/import-profiles/${profile.id}`, { method: 'PUT', body })
        : api<ImportProfile>('/catalog/import-profiles', { method: 'POST', body })
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ['import-profiles'] })
      onSaved(saved)
    },
  })

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-6 shadow-xs">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <div className="w-40">
            <Field id="map_header" label="Ligne des titres">
              <Input
                id="map_header"
                type="number"
                min={1}
                max={50}
                value={settings.header_row}
                onChange={(e) => setSettings({ ...settings, header_row: Math.max(1, Number(e.target.value) || 1) })}
              />
            </Field>
          </div>
          {data?.file_format === 'excel' && data.sheets && data.sheets.length > 1 && (
            <div className="w-56">
              <Field id="map_sheet" label="Onglet">
                <NativeSelect id="map_sheet" value={settings.sheet_name || data.sheet_name || ''} onChange={(e) => setSettings({ ...settings, sheet_name: e.target.value })}>
                  {data.sheets.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </NativeSelect>
              </Field>
            </div>
          )}
          {data?.file_format === 'csv' && (
            <>
              <div className="w-44">
                <Field id="map_delim" label="Séparateur">
                  <NativeSelect id="map_delim" value={settings.delimiter} onChange={(e) => setSettings({ ...settings, delimiter: e.target.value })}>
                    <option value="">Détecté ({data.delimiter === '\t' ? 'tabulation' : data.delimiter})</option>
                    <option value=";">Point-virgule ;</option>
                    <option value=",">Virgule ,</option>
                    <option value={'\t'}>Tabulation</option>
                    <option value="|">Barre |</option>
                  </NativeSelect>
                </Field>
              </div>
              <div className="w-52">
                <Field id="map_enc" label="Encodage">
                  <NativeSelect id="map_enc" value={settings.encoding} onChange={(e) => setSettings({ ...settings, encoding: e.target.value })}>
                    <option value="">Détecté ({data.encoding === 'cp1252' ? 'Windows' : 'UTF-8'})</option>
                    <option value="utf-8-sig">UTF-8</option>
                    <option value="cp1252">Windows (Excel français)</option>
                  </NativeSelect>
                </Field>
              </div>
            </>
          )}
          {preview.isFetching && <LoaderCircle className="mb-2 size-5 animate-spin text-muted-foreground" />}
        </div>
        <ErrorAlert error={preview.error} />
        {data && (
          <>
            <p className="mb-2 text-sm text-muted-foreground">
              Début du fichier <span className="font-medium text-foreground">{file.name}</span> — les colonnes utilisées sont surlignées.
            </p>
            <div className="max-h-80 overflow-auto rounded-lg border">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-secondary text-left">
                  <tr>
                    {headers.map((h) => (
                      <th key={h} className={cn('px-3 py-2 font-medium whitespace-nowrap', mappedHeaders.has(h) && 'bg-accent/25')}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j} className={cn('max-w-64 truncate px-3 py-1.5 whitespace-nowrap', mappedHeaders.has(headers[j]) && 'bg-accent/10')}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {data && (
        <section className="rounded-xl border bg-card p-6 shadow-xs">
          <h2 className="font-semibold">À quoi correspond chaque colonne ?</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Proposition automatique d'après les titres : vérifiez-la. Obligatoire : le prix d'achat, et le code EAN ou la référence fournisseur.
          </p>
          {lost.length > 0 && (
            <p className="mb-4 rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-800">
              Colonnes absentes de ce fichier : {lost.map(([, h]) => `« ${h} »`).join(', ')}. Le fournisseur a peut-être changé son format.
            </p>
          )}
          <div className="space-y-6">
            {FIELD_GROUPS.map((group) => (
              <div key={group.title}>
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{group.title}</h3>
                <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                  {group.fields.map((f) => (
                    <label key={f} className="grid gap-1 text-sm">
                      <span className="flex items-center gap-1">
                        {data.fields[f]}
                        {(f === 'purchase_price' || f === 'ean' || f === 'supplier_ref') && <span className="text-destructive">*</span>}
                      </span>
                      <NativeSelect
                        aria-label={data.fields[f]}
                        value={current[f] ?? ''}
                        onChange={(e) => {
                          const next = { ...current }
                          if (e.target.value) next[f] = e.target.value
                          else delete next[f]
                          setMapping(next)
                        }}
                      >
                        <option value="">— Non utilisé —</option>
                        {headers.map((h) => (
                          <option key={h} value={h}>
                            {h}
                            {mappedHeaders.has(h) && current[f] !== h ? ' (déjà utilisée)' : ''}
                          </option>
                        ))}
                      </NativeSelect>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data && (
        <section className="rounded-xl border bg-card p-6 shadow-xs">
          <h2 className="mb-4 font-semibold">Options</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field id="map_name" label="Nom du format">
              <Input id="map_name" value={options.name} onChange={(e) => setOptions({ ...options, name: e.target.value })} />
            </Field>
            <Field id="map_kind" label="Type d'article par défaut" hint="Quand le fichier n'a pas de colonne « type »">
              <NativeSelect id="map_kind" value={options.default_kind} onChange={(e) => setOptions({ ...options, default_kind: e.target.value as Kind })}>
                {Object.entries(KINDS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {options.default_kind === 'pneu' && (
              <Field id="map_vehicle" label="Véhicule par défaut" hint="Sinon déduit de la dimension (C = utilitaire, 22.5 = PL)">
                <NativeSelect id="map_vehicle" value={options.default_vehicle_type} onChange={(e) => setOptions({ ...options, default_vehicle_type: e.target.value })}>
                  <option value="">Tourisme</option>
                  {Object.entries(VEHICLE_TYPES).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            )}
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <CheckRow
              checked={options.full_catalog}
              onChange={(on) => setOptions({ ...options, full_catalog: on })}
              title="Fichier complet : un article absent du fichier est arrêté"
              description="À décocher pour un fichier partiel (promotions, nouveautés) : les articles absents restent actifs."
            />
            {options.default_kind === 'pneu' && (
              <CheckRow
                checked={options.parse_designation}
                onChange={(on) => setOptions({ ...options, parse_designation: on })}
                title="Lire la dimension dans la désignation"
                description="« 205/55 R16 91V XL » → largeur, série, jante, indices, XL… quand il n'y a pas de colonnes dédiées."
              />
            )}
          </div>
        </section>
      )}

      <ErrorAlert error={save.error ?? uploadError} />
      <div className="flex flex-wrap items-center justify-end gap-3">
        {missing.length > 0 && data && <span className="text-sm text-destructive">Indiquez {missing.join(' et ')}.</span>}
        <Button variant="outline" onClick={onBack}>
          Retour
        </Button>
        <Button disabled={!data || missing.length > 0 || save.isPending || uploading} onClick={() => save.mutate()}>
          {(save.isPending || uploading) && <LoaderCircle className="animate-spin" />}
          Enregistrer le format et analyser
        </Button>
      </div>
    </div>
  )
}

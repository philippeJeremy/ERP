import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { gtinIsValid, KINDS, SEASONS, VEHICLE_TYPES, type Article } from '@/pages/catalog/types'

const num = (re: RegExp, msg: string) => z.string().trim().refine((v) => v === '' || re.test(v), msg)
const schema = z
  .object({
    kind: z.enum(['pneu', 'piece', 'accessoire']),
    designation: z.string().trim().max(250),
    brand: z.string().trim().max(100),
    ean: z.string().refine((v) => v.trim() === '' || gtinIsValid(v.replace(/\s/g, '')), 'EAN invalide (clé de contrôle)'),
    manufacturer_ref: z.string().trim().max(50),
    category: z.string().trim().max(100),
    vehicle_type: z.string(),
    season: z.string(),
    width: num(/^\d{1,3}([.,]\d{1,2})?$/, 'Ex. 205 ou 12,5'),
    aspect_ratio: num(/^\d{2,3}$/, 'Ex. 55'),
    construction: z.string(),
    rim: num(/^\d{1,2}([.,]\d)?$/, 'Ex. 16 ou 22,5'),
    load_index: num(/^\d{1,3}(\/\d{1,3})?$/, 'Ex. 91 ou 154/150'),
    speed_index: num(/^[A-Za-z]\d?$/, 'Une lettre : H, V, W…'),
    reinforced: z.boolean(),
    runflat: z.boolean(),
    three_pmsf: z.boolean(),
    mud_snow: z.boolean(),
    studded: z.boolean(),
    fuel_class: z.string(),
    wet_class: z.string(),
    noise_db: num(/^\d{2}$/, 'Entre 50 et 90'),
    noise_class: z.string(),
    eprel_id: z.string().trim().max(20),
  })
  .refine((v) => v.kind === 'pneu' || v.designation !== '', { path: ['designation'], message: 'Désignation requise' })
type Values = z.infer<typeof schema>

function Group({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 border-t pt-4">
      <legend className="float-left w-full text-sm font-semibold">
        {title}
        {hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}
      </legend>
      <div className="clear-both grid gap-4 sm:grid-cols-4">{children}</div>
    </fieldset>
  )
}

export function ArticleDialog({ article, onClose, onSaved }: { article: Article | null; onClose: () => void; onSaved?: (a: Article) => void }) {
  const queryClient = useQueryClient()
  const t = article?.tire
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      kind: article?.kind ?? 'pneu',
      designation: article?.designation ?? '',
      brand: article?.brand?.name ?? '',
      ean: article?.ean ?? '',
      manufacturer_ref: article?.manufacturer_ref ?? '',
      category: article?.category ?? '',
      vehicle_type: t?.vehicle_type ?? 'tourisme',
      season: t?.season ?? '',
      width: t?.width ? String(Number(t.width)) : '',
      aspect_ratio: t?.aspect_ratio?.toString() ?? '',
      construction: t?.construction ?? 'R',
      rim: t?.rim ? String(Number(t.rim)) : '',
      load_index: t?.load_index ?? '',
      speed_index: t?.speed_index ?? '',
      reinforced: t?.reinforced ?? false,
      runflat: t?.runflat ?? false,
      three_pmsf: t?.three_pmsf ?? false,
      mud_snow: t?.mud_snow ?? false,
      studded: t?.studded ?? false,
      fuel_class: t?.fuel_class ?? '',
      wet_class: t?.wet_class ?? '',
      noise_db: t?.noise_db?.toString() ?? '',
      noise_class: t?.noise_class ?? '',
      eprel_id: t?.eprel_id ?? '',
    },
  })
  const errors = form.formState.errors
  const kind = useWatch({ control: form.control, name: 'kind' })
  const flags = useWatch({ control: form.control, name: ['reinforced', 'runflat', 'three_pmsf', 'mud_snow', 'studded'] })
  const brands = useQuery({ queryKey: ['brands'], queryFn: () => api<{ id: number; name: string }[]>('/catalog/brands') })

  const save = useMutation({
    mutationFn: (v: Values) => {
      const n = (s: string) => (s === '' ? null : s)
      const tire =
        v.kind === 'pneu'
          ? {
              vehicle_type: v.vehicle_type,
              season: n(v.season),
              width: n(v.width.replace(',', '.')),
              aspect_ratio: v.aspect_ratio ? Number(v.aspect_ratio) : null,
              construction: n(v.construction),
              rim: n(v.rim.replace(',', '.')),
              load_index: n(v.load_index),
              speed_index: n(v.speed_index.toUpperCase()),
              reinforced: v.reinforced,
              runflat: v.runflat,
              three_pmsf: v.three_pmsf,
              mud_snow: v.mud_snow,
              studded: v.studded,
              fuel_class: n(v.fuel_class),
              wet_class: n(v.wet_class),
              noise_db: v.noise_db ? Number(v.noise_db) : null,
              noise_class: n(v.noise_class),
              eprel_id: n(v.eprel_id),
            }
          : null
      const body = {
        designation: n(v.designation),
        brand: n(v.brand),
        ean: n(v.ean.replace(/\s/g, '')),
        manufacturer_ref: n(v.manufacturer_ref),
        category: n(v.category),
        tire,
      }
      return article
        ? api<Article>(`/catalog/articles/${article.id}`, { method: 'PATCH', body: { ...body, version: article.version } })
        : api<Article>('/catalog/articles', { method: 'POST', body: { ...body, kind: v.kind } })
    },
    onSuccess: async (saved) => {
      queryClient.setQueriesData<Article>({ queryKey: ['article'] }, (old) => (old?.id === saved.id ? saved : old))
      await queryClient.invalidateQueries({ queryKey: ['articles'] })
      void queryClient.invalidateQueries({ queryKey: ['brands'] })
      onSaved?.(saved)
      onClose()
    },
  })

  const text = (name: keyof Values, label: string, extra?: { span?: string; mono?: boolean; hint?: string; placeholder?: string }) => (
    <div className={extra?.span}>
      <Field id={`art_${name}`} label={label} error={errors[name]?.message} hint={extra?.hint}>
        <Input
          id={`art_${name}`}
          autoComplete="off"
          placeholder={extra?.placeholder}
          className={extra?.mono ? 'font-mono' : undefined}
          list={name === 'brand' ? 'brand-list' : undefined}
          {...form.register(name)}
        />
      </Field>
    </div>
  )
  const select = (name: keyof Values, label: string, options: Record<string, string>, empty?: string) => (
    <Field id={`art_${name}`} label={label}>
      <NativeSelect id={`art_${name}`} {...form.register(name)}>
        {empty !== undefined && <option value="">{empty}</option>}
        {Object.entries(options).map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </NativeSelect>
    </Field>
  )
  const letters = (list: string) => Object.fromEntries(list.split('').map((l) => [l, l]))
  const flag = (name: 'reinforced' | 'runflat' | 'three_pmsf' | 'mud_snow' | 'studded', label: string, index: number) => (
    <CheckRow className="py-2" checked={flags[index]} onChange={(on) => form.setValue(name, on, { shouldDirty: true })} title={label} />
  )

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{article ? `Modifier ${article.code}` : 'Nouvel article'}</DialogTitle>
          <DialogDescription>
            Le catalogue est commun à toutes les sociétés du groupe : la fiche sera visible de toutes. Les prix d'achat, eux,
            restent propres à chaque société.
          </DialogDescription>
        </DialogHeader>
        <datalist id="brand-list">
          {brands.data?.map((b) => <option key={b.id} value={b.name} />)}
        </datalist>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-5" noValidate>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field id="art_kind" label="Type">
              <NativeSelect id="art_kind" disabled={!!article} {...form.register('kind')}>
                {Object.entries(KINDS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {text('brand', 'Marque', { span: 'sm:col-span-1' })}
            {text('ean', 'Code EAN', { span: 'sm:col-span-2', mono: true, hint: 'Le code-barres (13 chiffres)' })}
            {text('designation', 'Désignation', {
              span: 'sm:col-span-4',
              hint: kind === 'pneu' ? 'Vide : construite à partir de la marque et de la dimension' : undefined,
            })}
            {text('manufacturer_ref', 'Référence fabricant', { span: 'sm:col-span-2', mono: true, hint: 'CAI, code article de la marque' })}
            {kind !== 'pneu' && text('category', 'Catégorie', { span: 'sm:col-span-2', placeholder: 'Valves, chaînes neige, outillage…' })}
          </div>

          {kind === 'pneu' && (
            <>
              <Group title="Dimension" hint="205/55 R16 91V">
                {text('width', 'Largeur', { placeholder: '205' })}
                {text('aspect_ratio', 'Série', { placeholder: '55' })}
                {select('construction', 'Structure', { R: 'R (radial)', ZR: 'ZR', D: 'D (diagonal)', B: 'B', '-': '-' })}
                {text('rim', 'Jante', { placeholder: '16' })}
                {text('load_index', 'Indice de charge', { placeholder: '91' })}
                {text('speed_index', 'Indice de vitesse', { placeholder: 'V' })}
                {select('vehicle_type', 'Véhicule', VEHICLE_TYPES)}
                {select('season', 'Saison', SEASONS, '—')}
              </Group>
              <Group title="Particularités">
                {flag('reinforced', 'XL / renforcé', 0)}
                {flag('runflat', 'Runflat', 1)}
                {flag('three_pmsf', '3PMSF (flocon)', 2)}
                {flag('mud_snow', 'M+S', 3)}
                {flag('studded', 'Clouté', 4)}
              </Group>
              <Group title="Étiquette européenne">
                {select('fuel_class', 'Carburant', letters('ABCDE'), '—')}
                {select('wet_class', 'Adhérence', letters('ABCDE'), '—')}
                {text('noise_db', 'Bruit (dB)', { placeholder: '70' })}
                {select('noise_class', 'Classe de bruit', letters('ABC'), '—')}
                {text('eprel_id', 'N° EPREL', { span: 'sm:col-span-2', mono: true, hint: 'Fiche produit de la base européenne' })}
              </Group>
            </>
          )}
          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <LoaderCircle className="animate-spin" />}
              {article ? 'Enregistrer' : "Créer l'article"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

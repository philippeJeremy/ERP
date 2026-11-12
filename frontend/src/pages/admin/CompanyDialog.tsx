import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import type { Company } from '@/lib/types'

// Champs facultatifs : chaîne vide acceptée dans le formulaire, envoyée comme « null ».
const optional = (max: number) => z.string().trim().max(max)
const schema = z.object({
  code: z
    .string()
    .trim()
    .min(1, 'Code requis')
    .max(20)
    .regex(/^[A-Z0-9_-]+$/, 'Majuscules, chiffres, - et _ uniquement'),
  name: z.string().trim().min(1, 'Raison sociale requise').max(200),
  legal_form: optional(50),
  siren: z.string().trim().regex(/^(\d{9})?$/, '9 chiffres'),
  vat_number: optional(20),
  address_line1: optional(200),
  address_line2: optional(200),
  postal_code: optional(10),
  city: optional(100),
  country_code: z.string().trim().regex(/^[A-Z]{2}$/, '2 lettres (FR, BE…)'),
  email: z.union([z.literal(''), z.email('Adresse e-mail invalide')]),
  phone: optional(30),
  iban: optional(34),
  bic: optional(11),
  currency: z.string().trim().regex(/^[A-Z]{3}$/, '3 lettres (EUR…)'),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 border-t pt-4 first:border-t-0 first:pt-0">
      <legend className="float-left mb-3 w-full text-sm font-semibold">{title}</legend>
      <div className="clear-both grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

export function CompanyDialog({
  company,
  isSuperuser,
  onClose,
}: {
  company: Company | null
  isSuperuser: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: company?.code ?? '',
      name: company?.name ?? '',
      legal_form: company?.legal_form ?? '',
      siren: company?.siren ?? '',
      vat_number: company?.vat_number ?? '',
      address_line1: company?.address_line1 ?? '',
      address_line2: company?.address_line2 ?? '',
      postal_code: company?.postal_code ?? '',
      city: company?.city ?? '',
      country_code: company?.country_code ?? 'FR',
      email: company?.email ?? '',
      phone: company?.phone ?? '',
      iban: company?.iban ?? '',
      bic: company?.bic ?? '',
      currency: company?.currency ?? 'EUR',
      is_active: company?.is_active ?? true,
    },
  })
  const errors = form.formState.errors
  const active = useWatch({ control: form.control, name: 'is_active' })

  const save = useMutation({
    mutationFn: (v: Values) => {
      const { code, is_active, ...rest } = v
      const body: Record<string, unknown> = Object.fromEntries(
        Object.entries(rest).map(([k, value]) => [k, value === '' ? null : value]),
      )
      if (!company) return api<Company>('/org/companies', { method: 'POST', body: { ...body, code } })
      // `version` : celle affichée à l'ouverture. Si quelqu'un a modifié la fiche
      // entre-temps, l'API refuse (409) au lieu d'écraser son travail.
      if (isSuperuser) body.is_active = is_active
      return api<Company>(`/org/companies/${company.id}`, { method: 'PATCH', body: { ...body, version: company.version } })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['companies'] })
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      onClose()
    },
  })
  const text = (name: keyof Omit<Values, 'is_active'>, label: string, extra?: { hint?: string; className?: string; mono?: boolean; disabled?: boolean }) => (
    <div className={extra?.className}>
      <Field id={`company_${name}`} label={label} error={errors[name]?.message} hint={extra?.hint}>
        <Input id={`company_${name}`} autoComplete="off" disabled={extra?.disabled} className={extra?.mono ? 'font-mono' : undefined} {...form.register(name)} />
      </Field>
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{company ? `Modifier « ${company.name} »` : 'Nouvelle société'}</DialogTitle>
          <DialogDescription>
            {company
              ? 'Ces informations apparaîtront sur les documents (factures, devis).'
              : 'Ses compteurs de numérotation sont créés automatiquement et vous en devenez administrateur.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-5" noValidate>
          <Group title="Identité">
            {text('name', 'Raison sociale', { className: 'sm:col-span-2' })}
            {text('code', 'Code', {
              mono: true,
              disabled: !!company,
              hint: company ? 'Le code ne se modifie pas.' : 'Court et en majuscules : HOLD, FIL-NORD…',
            })}
            {text('legal_form', 'Forme juridique', { hint: 'SAS, SARL, SA…' })}
            {text('siren', 'SIREN', { mono: true })}
            {text('vat_number', 'N° de TVA intracommunautaire', { mono: true })}
          </Group>
          <Group title="Adresse">
            {text('address_line1', 'Adresse', { className: 'sm:col-span-2' })}
            {text('address_line2', "Complément d'adresse", { className: 'sm:col-span-2' })}
            {text('postal_code', 'Code postal')}
            {text('city', 'Ville')}
            {text('country_code', 'Pays', { mono: true })}
          </Group>
          <Group title="Contact et banque">
            {text('email', 'E-mail')}
            {text('phone', 'Téléphone')}
            {text('iban', 'IBAN', { mono: true })}
            {text('bic', 'BIC', { mono: true })}
            {text('currency', 'Devise', { mono: true })}
          </Group>
          {company && isSuperuser && (
            <CheckRow
              checked={active}
              onChange={(on) => form.setValue('is_active', on, { shouldDirty: true })}
              title="Société active"
              description="Décochée : ses utilisateurs n'y ont plus accès, mais toutes ses données sont conservées. C'est ce qu'il faut faire pour une société qui a déjà des documents."
            />
          )}
          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <LoaderCircle className="animate-spin" />}
              {company ? 'Enregistrer' : 'Créer la société'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

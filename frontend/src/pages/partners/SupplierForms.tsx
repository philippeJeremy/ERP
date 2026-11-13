import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useForm, useWatch, type FieldValues, type Path, type UseFormReturn } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { gtinIsValid } from '@/pages/catalog/types'
import { compact, CUSTOMER_KINDS, formatIban, ibanIsValid, PAYMENT_METHODS, type Partner } from '@/pages/partners/types'

// Dans les formulaires, un champ vide est une chaîne vide ; à l'envoi elle devient null.
const text = (max: number) => z.string().trim().max(max, `${max} caractères maximum`)
const integer = (min: number, max: number) =>
  z
    .string()
    .trim()
    .refine((v) => v === '' || (/^\d+$/.test(v) && Number(v) >= min && Number(v) <= max), `Nombre entier de ${min} à ${max}`)
const amount = z
  .string()
  .trim()
  .refine((v) => v === '' || /^\d{1,12}([.,]\d{1,2})?$/.test(v), 'Montant invalide (ex. 1500 ou 99,90)')

const toBody = (values: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === '' ? null : v]))

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid gap-x-8 gap-y-4 border-t py-6 first:border-t-0 first:pt-0 lg:grid-cols-[14rem_1fr]">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  )
}

/** Enregistre les changements de la fiche (PATCH avec la version : verrouillage optimiste). */
function useSavePartner<T extends FieldValues>(
  partner: Partner,
  form: UseFormReturn<T>,
  transform: (v: T) => Record<string, unknown>,
  defaults: (p: Partner) => T,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: T) =>
      api<Partner>(`/partners/${partner.id}`, { method: 'PATCH', body: { ...transform(v), version: partner.version } }),
    onSuccess: (saved) => {
      queryClient.setQueriesData<Partner>({ queryKey: ['partner'] }, (old) => (old?.id === saved.id ? saved : old))
      void queryClient.invalidateQueries({ queryKey: ['partners'] })
      // Repart des valeurs enregistrées (nettoyées par l'API : SIRET sans espaces…).
      form.reset(defaults(saved))
    },
  })
}

function SaveBar({ form, save, disabled }: { form: UseFormReturn<never>; save: { isPending: boolean; isSuccess: boolean; error: unknown }; disabled: boolean }) {
  if (disabled) return null
  const dirty = form.formState.isDirty
  return (
    <div className="sticky bottom-0 -mx-6 flex items-center justify-end gap-3 border-t bg-card/95 px-6 py-3 backdrop-blur">
      {!dirty && save.isSuccess && (
        <span className="flex items-center gap-1 text-sm text-emerald-700">
          <Check className="size-4" /> Enregistré
        </span>
      )}
      {dirty && (
        <Button type="button" variant="outline" onClick={() => form.reset()}>
          Annuler les modifications
        </Button>
      )}
      <Button type="submit" disabled={!dirty || save.isPending}>
        {save.isPending && <LoaderCircle className="animate-spin" />}
        Enregistrer
      </Button>
    </div>
  )
}

function TextField<T extends FieldValues>({
  form,
  name,
  label,
  hint,
  className,
  mono,
  disabled,
  type,
}: {
  form: UseFormReturn<T>
  name: Path<T>
  label: string
  hint?: string
  className?: string
  mono?: boolean
  disabled: boolean
  type?: string
}) {
  const error = form.formState.errors[name]?.message as string | undefined
  return (
    <div className={className}>
      <Field id={`p_${name}`} label={label} error={error} hint={hint}>
        <Input id={`p_${name}`} type={type} autoComplete="off" disabled={disabled} className={mono ? 'font-mono' : undefined} aria-invalid={!!error} {...form.register(name)} />
      </Field>
    </div>
  )
}

// --- Onglet « Informations » ------------------------------------------------------

const infoSchema = z.object({
  name: z.string().trim().min(1, 'Raison sociale requise').max(200),
  legal_form: text(50),
  siret: z.string().refine((v) => /^(\d{14})?$/.test(compact(v)), '14 chiffres'),
  vat_number: text(20),
  gln: z.string().refine((v) => v.trim() === '' || (compact(v).length === 13 && gtinIsValid(compact(v))), 'GLN invalide (13 chiffres, clé GS1)'),
  email: z.union([z.literal(''), z.email('Adresse e-mail invalide')]),
  phone: text(30),
  website: text(200),
  notes: z.string(),
  is_customer: z.boolean(),
  is_supplier: z.boolean(),
})
type InfoValues = z.infer<typeof infoSchema>

const infoDefaults = (p: Partner): InfoValues => ({
  name: p.name,
  legal_form: p.legal_form ?? '',
  siret: p.siret ?? '',
  vat_number: p.vat_number ?? '',
  gln: p.gln ?? '',
  email: p.email ?? '',
  phone: p.phone ?? '',
  website: p.website ?? '',
  notes: p.notes ?? '',
  is_customer: p.is_customer,
  is_supplier: p.is_supplier,
})

export function InfoForm({ partner, readOnly, role = 'supplier' }: { partner: Partner; readOnly: boolean; role?: 'supplier' | 'customer' }) {
  const form = useForm<InfoValues>({ resolver: zodResolver(infoSchema), defaultValues: infoDefaults(partner) })
  const save = useSavePartner(partner, form, toBody, infoDefaults)
  const isCustomer = useWatch({ control: form.control, name: 'is_customer' })
  const isSupplier = useWatch({ control: form.control, name: 'is_supplier' })
  const individual = role === 'customer' && partner.customer_kind === 'particulier'
  const f = { form, disabled: readOnly }

  return (
    <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
      {individual ? (
        <Section title="Identité" description="Le prénom et le véhicule sont dans l'onglet Conditions de vente.">
          <TextField {...f} name="name" label="Nom" className="sm:col-span-2" />
        </Section>
      ) : (
        <Section title="Identité" description="Telle qu'elle figure sur ses factures (Kbis).">
          <TextField {...f} name="name" label="Raison sociale" className="sm:col-span-2" />
          <TextField {...f} name="legal_form" label="Forme juridique" hint="SAS, SARL, SA…" />
          <TextField {...f} name="siret" label="SIRET" mono hint="Identifie l'établissement (14 chiffres)" />
          <TextField {...f} name="vat_number" label="N° de TVA intracommunautaire" mono />
          <TextField {...f} name="gln" label="GLN" mono hint="Identifiant GS1 de l'entreprise, pour l'EDI" />
        </Section>
      )}
      <Section title="Coordonnées" description="Le standard. Les interlocuteurs sont dans l'onglet Contacts.">
        <TextField {...f} name="email" label="E-mail" type="email" />
        <TextField {...f} name="phone" label="Téléphone" type="tel" />
        <TextField {...f} name="website" label="Site web" className="sm:col-span-2" />
      </Section>
      <Section title="Notes" description="Visibles de tous les utilisateurs de la société.">
        <div className="sm:col-span-2">
          <Textarea id="p_notes" aria-label="Notes" disabled={readOnly} rows={4} {...form.register('notes')} />
        </div>
      </Section>
      <Section title="Rôles" description="Une même entreprise peut être fournisseur et cliente : une seule fiche.">
        {role === 'supplier' ? (
          <CheckRow
            className="sm:col-span-2"
            checked={isCustomer}
            disabled={readOnly}
            onChange={(on) => form.setValue('is_customer', on, { shouldDirty: true })}
            title="Aussi client"
            description="Il apparaîtra aussi dans les clients : devis, commandes, livraisons."
          />
        ) : (
          <CheckRow
            className="sm:col-span-2"
            checked={isSupplier}
            disabled={readOnly}
            onChange={(on) => form.setValue('is_supplier', on, { shouldDirty: true })}
            title="Aussi fournisseur"
            description="Il apparaîtra aussi dans les fournisseurs : articles, commandes d'achat."
          />
        )}
      </Section>
      <ErrorAlert error={save.error} />
      <SaveBar form={form as never} save={save} disabled={readOnly} />
    </form>
  )
}

// --- Onglet « Conditions d'achat et banque » ---------------------------------------

const termsSchema = z.object({
  supplier_account: text(20),
  payment_method: z.string(),
  payment_days: integer(0, 120),
  payment_end_of_month: z.boolean(),
  currency: z.string().trim().toUpperCase().regex(/^[A-Z]{3}$/, '3 lettres (EUR, USD…)'),
  lead_time_days: integer(0, 365),
  min_order_amount: amount,
  free_shipping_amount: amount,
  bank_name: text(100),
  iban: z.string().refine((v) => v.trim() === '' || ibanIsValid(v), 'IBAN invalide : vérifiez les caractères (clé de contrôle)'),
  bic: z.string().refine((v) => /^([A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?)?$/.test(compact(v)), '8 ou 11 caractères (ex. BNPAFRPP)'),
})
type TermsValues = z.infer<typeof termsSchema>

const termsDefaults = (p: Partner): TermsValues => ({
  supplier_account: p.supplier_account ?? '',
  payment_method: p.payment_method ?? '',
  payment_days: p.payment_days?.toString() ?? '',
  payment_end_of_month: p.payment_end_of_month,
  currency: p.currency,
  lead_time_days: p.lead_time_days?.toString() ?? '',
  min_order_amount: p.min_order_amount ?? '',
  free_shipping_amount: p.free_shipping_amount ?? '',
  bank_name: p.bank_name ?? '',
  iban: p.iban ? formatIban(p.iban) : '',
  bic: p.bic ?? '',
})

export function TermsForm({ partner, readOnly }: { partner: Partner; readOnly: boolean }) {
  const form = useForm<TermsValues>({ resolver: zodResolver(termsSchema), defaultValues: termsDefaults(partner) })
  const save = useSavePartner(
    partner,
    form,
    (v) => {
      const body = toBody(v)
      for (const k of ['payment_days', 'lead_time_days'] as const) body[k] = v[k] === '' ? null : Number(v[k])
      for (const k of ['min_order_amount', 'free_shipping_amount'] as const)
        body[k] = v[k] === '' ? null : v[k].replace(',', '.')
      return body
    },
    termsDefaults,
  )
  const endOfMonth = useWatch({ control: form.control, name: 'payment_end_of_month' })
  const f = { form, disabled: readOnly }

  return (
    <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
      <Section title="Règlement" description="Repris sur les commandes fournisseur, et pour calculer les échéances des factures.">
        <Field id="p_payment_method" label="Mode de règlement">
          <NativeSelect id="p_payment_method" disabled={readOnly} {...form.register('payment_method')}>
            <option value="">— Non précisé —</option>
            {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <TextField {...f} name="payment_days" label="Délai de paiement (jours)" hint="0 = comptant ; 30, 45, 60…" />
        <CheckRow
          className="sm:col-span-2"
          checked={endOfMonth}
          disabled={readOnly}
          onChange={(on) => form.setValue('payment_end_of_month', on, { shouldDirty: true })}
          title="Fin de mois"
          description="« 45 jours fin de mois » : l'échéance est reportée à la fin du mois."
        />
        <TextField {...f} name="currency" label="Devise" mono />
        <TextField {...f} name="supplier_account" label="Compte comptable" mono hint="Compte fournisseur (401…)" />
      </Section>
      <Section title="Commande et livraison">
        <TextField {...f} name="lead_time_days" label="Délai de livraison habituel (jours)" />
        <div className="hidden sm:block" />
        <TextField {...f} name="min_order_amount" label="Minimum de commande (HT)" hint="En dessous, le fournisseur refuse la commande" />
        <TextField {...f} name="free_shipping_amount" label="Franco de port (HT)" hint="Au-delà, la livraison est offerte" />
      </Section>
      <Section title="Coordonnées bancaires" description="Pour payer ses factures par virement. L'IBAN est vérifié (clé de contrôle).">
        <TextField {...f} name="bank_name" label="Banque" className="sm:col-span-2" />
        <TextField {...f} name="iban" label="IBAN" mono className="sm:col-span-2" />
        <TextField {...f} name="bic" label="BIC" mono />
      </Section>
      <ErrorAlert error={save.error} />
      <SaveBar form={form as never} save={save} disabled={readOnly} />
    </form>
  )
}

// --- Onglet « Conditions de vente » (clients) ------------------------------------

const pct = z
  .string()
  .trim()
  .refine((v) => v === '' || (/^\d{1,3}([.,]\d{1,2})?$/.test(v) && Number(v.replace(',', '.')) <= 100), 'Pourcentage de 0 à 100')

const customerSchema = z.object({
  customer_kind: z.enum(['pro', 'particulier']),
  first_name: text(100),
  vehicle_registration: text(15),
  customer_payment_method: z.string(),
  customer_payment_days: integer(0, 120),
  customer_payment_end_of_month: z.boolean(),
  credit_limit: amount,
  customer_account: text(20),
  discount_pct: pct,
  discount_tire_pct: pct,
  discount_part_pct: pct,
  discount_accessory_pct: pct,
})
type CustomerValues = z.infer<typeof customerSchema>

const num = (v: string | null) => (v === null ? '' : String(Number(v)).replace('.', ','))
const customerDefaults = (p: Partner): CustomerValues => ({
  customer_kind: p.customer_kind ?? 'pro',
  first_name: p.first_name ?? '',
  vehicle_registration: p.vehicle_registration ?? '',
  customer_payment_method: p.customer_payment_method ?? '',
  customer_payment_days: p.customer_payment_days?.toString() ?? '',
  customer_payment_end_of_month: p.customer_payment_end_of_month,
  credit_limit: p.credit_limit ?? '',
  customer_account: p.customer_account ?? '',
  discount_pct: num(p.discount_pct),
  discount_tire_pct: num(p.discount_tire_pct),
  discount_part_pct: num(p.discount_part_pct),
  discount_accessory_pct: num(p.discount_accessory_pct),
})

export function CustomerTermsForm({ partner, readOnly }: { partner: Partner; readOnly: boolean }) {
  const form = useForm<CustomerValues>({ resolver: zodResolver(customerSchema), defaultValues: customerDefaults(partner) })
  const save = useSavePartner(
    partner,
    form,
    (v) => {
      const body = toBody(v)
      body.customer_payment_days = v.customer_payment_days === '' ? null : Number(v.customer_payment_days)
      for (const k of ['credit_limit', 'discount_tire_pct', 'discount_part_pct', 'discount_accessory_pct'] as const)
        body[k] = v[k] === '' ? null : v[k].replace(',', '.')
      body.discount_pct = v.discount_pct === '' ? '0' : v.discount_pct.replace(',', '.')
      return body
    },
    customerDefaults,
  )
  const endOfMonth = useWatch({ control: form.control, name: 'customer_payment_end_of_month' })
  const kind = useWatch({ control: form.control, name: 'customer_kind' })
  const f = { form, disabled: readOnly }
  return (
    <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
      <Section title="Profil" description="Un particulier est servi au comptoir : nom, prénom, véhicule.">
        <Field id="p_customer_kind" label="Type de client">
          <NativeSelect id="p_customer_kind" disabled={readOnly} {...form.register('customer_kind')}>
            {Object.entries(CUSTOMER_KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {kind === 'particulier' ? <TextField {...f} name="first_name" label="Prénom" /> : <div className="hidden sm:block" />}
        <TextField {...f} name="vehicle_registration" label="Immatriculation" mono hint="AB-123-CD : reprise sur les devis et BL" />
      </Section>
      <Section title="Remises" description="Appliquées automatiquement sur le tarif de vente. Vide = la remise générale.">
        <TextField {...f} name="discount_pct" label="Remise générale (%)" />
        <div className="hidden sm:block" />
        <TextField {...f} name="discount_tire_pct" label="Pneus (%)" />
        <TextField {...f} name="discount_part_pct" label="Pièces (%)" />
        <TextField {...f} name="discount_accessory_pct" label="Accessoires (%)" />
      </Section>
      <Section title="Règlement et encours" description="L'encours est contrôlé à la confirmation des commandes.">
        <Field id="p_customer_payment_method" label="Mode de règlement">
          <NativeSelect id="p_customer_payment_method" disabled={readOnly} {...form.register('customer_payment_method')}>
            <option value="">— Non précisé —</option>
            {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <TextField {...f} name="customer_payment_days" label="Délai de paiement (jours)" hint="0 = comptant" />
        <CheckRow
          className="sm:col-span-2"
          checked={endOfMonth}
          disabled={readOnly}
          onChange={(on) => form.setValue('customer_payment_end_of_month', on, { shouldDirty: true })}
          title="Fin de mois"
        />
        <TextField {...f} name="credit_limit" label="Encours autorisé (TTC)" hint="Vide = pas de limite" />
        <TextField {...f} name="customer_account" label="Compte comptable" mono hint="Compte client (411…)" />
      </Section>
      <ErrorAlert error={save.error} />
      <SaveBar form={form as never} save={save} disabled={readOnly} />
    </form>
  )
}

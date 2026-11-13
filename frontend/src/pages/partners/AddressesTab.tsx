import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, MapPin, Pencil, Plus, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { gtinIsValid } from '@/pages/catalog/types'
import { ADDRESS_KINDS, type AddressKind, type Partner, type PartnerAddress } from '@/pages/partners/types'

// Pour un fournisseur, l'adresse « livraison » (clients) est rarement utile : en dernier.
const KIND_ORDER: AddressKind[] = ['siege', 'commande', 'enlevement', 'retour', 'facturation', 'livraison', 'autre']

export function AddressesTab({ partner, readOnly }: { partner: Partner; readOnly: boolean }) {
  const [editing, setEditing] = useState<PartnerAddress | 'new' | null>(null)
  const queryClient = useQueryClient()
  const remove = useMutation({
    mutationFn: (a: PartnerAddress) => api<void>(`/partners/${partner.id}/addresses/${a.id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['partner'] }),
  })
  const kinds = KIND_ORDER.filter((k) => partner.addresses.some((a) => a.kind === k))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Une adresse par usage : le siège, où envoyer les commandes, où enlever la marchandise, où renvoyer les retours…
          La principale de chaque type est utilisée par défaut sur les documents.
        </p>
        {!readOnly && (
          <Button onClick={() => setEditing('new')}>
            <Plus /> Ajouter une adresse
          </Button>
        )}
      </div>
      <ErrorAlert error={remove.error} />

      {partner.addresses.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
          <MapPin className="size-6" />
          Aucune adresse.
        </div>
      )}

      {kinds.map((kind) => (
        <section key={kind} className="space-y-2">
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{ADDRESS_KINDS[kind].label}</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {partner.addresses
              .filter((a) => a.kind === kind)
              .map((a) => (
                <div key={a.id} className="flex gap-3 rounded-xl border bg-card p-4 shadow-xs">
                  <div className="min-w-0 flex-1 text-sm leading-6">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {a.label || ADDRESS_KINDS[kind].label}
                      {a.is_primary && (
                        <Badge variant="accent">
                          <Star /> Principale
                        </Badge>
                      )}
                    </p>
                    <p>{a.line1}</p>
                    {a.line2 && <p>{a.line2}</p>}
                    <p>
                      {a.postal_code} {a.city}
                      {a.country_code !== 'FR' && ` · ${a.country_code}`}
                    </p>
                  </div>
                  {!readOnly && (
                    <div className="flex flex-col gap-1">
                      <Button variant="ghost" size="icon" title="Modifier" aria-label={`Modifier l'adresse ${a.line1}`} onClick={() => setEditing(a)}>
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        title="Supprimer"
                        aria-label={`Supprimer l'adresse ${a.line1}`}
                        disabled={remove.isPending}
                        onClick={() => window.confirm(`Supprimer l'adresse « ${a.line1}, ${a.city} » ?`) && remove.mutate(a)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  )}
                </div>
              ))}
          </div>
        </section>
      ))}

      {editing && (
        <AddressDialog partner={partner} address={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

const schema = z.object({
  kind: z.enum(KIND_ORDER),
  label: z.string().trim().max(100),
  line1: z.string().trim().min(1, 'Adresse requise').max(200),
  line2: z.string().trim().max(200),
  postal_code: z.string().trim().min(1, 'Code postal requis').max(10),
  city: z.string().trim().min(1, 'Ville requise').max(100),
  country_code: z.string().trim().toUpperCase().regex(/^[A-Z]{2}$/, '2 lettres (FR, BE, DE…)'),
  gln: z.string().refine((v) => v.trim() === '' || (v.replace(/\s/g, '').length === 13 && gtinIsValid(v.replace(/\s/g, ''))), 'GLN invalide'),
  is_primary: z.boolean(),
})
type Values = z.infer<typeof schema>

function AddressDialog({ partner, address, onClose }: { partner: Partner; address: PartnerAddress | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      // Première adresse : le siège, en toute logique.
      kind: address?.kind ?? (partner.addresses.some((a) => a.kind === 'siege') ? 'commande' : 'siege'),
      label: address?.label ?? '',
      line1: address?.line1 ?? '',
      line2: address?.line2 ?? '',
      postal_code: address?.postal_code ?? '',
      city: address?.city ?? '',
      country_code: address?.country_code ?? 'FR',
      gln: address?.gln ?? '',
      is_primary: address?.is_primary ?? false,
    },
  })
  const errors = form.formState.errors
  const kind = useWatch({ control: form.control, name: 'kind' })
  const primary = useWatch({ control: form.control, name: 'is_primary' })
  const firstOfKind = !partner.addresses.some((a) => a.kind === kind && a.id !== address?.id)

  const save = useMutation({
    mutationFn: (v: Values) => {
      const body = { ...v, label: v.label || null, line2: v.line2 || null, gln: v.gln.replace(/\s/g, '') || null }
      return address
        ? api(`/partners/${partner.id}/addresses/${address.id}`, { method: 'PUT', body })
        : api(`/partners/${partner.id}/addresses`, { method: 'POST', body })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['partner'] })
      void queryClient.invalidateQueries({ queryKey: ['partners'] }) // la ville de la liste
      onClose()
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{address ? "Modifier l'adresse" : 'Nouvelle adresse'}</DialogTitle>
          <DialogDescription>{partner.name}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="addr_kind" label="Type" hint={ADDRESS_KINDS[kind].hint}>
              <NativeSelect id="addr_kind" {...form.register('kind')}>
                {KIND_ORDER.map((k) => (
                  <option key={k} value={k}>
                    {ADDRESS_KINDS[k].label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="addr_label" label="Libellé (facultatif)" error={errors.label?.message} hint="Ex. « Entrepôt de Lyon »">
              <Input id="addr_label" autoComplete="off" {...form.register('label')} />
            </Field>
          </div>
          <Field id="addr_line1" label="Adresse" error={errors.line1?.message}>
            <Input id="addr_line1" autoComplete="off" {...form.register('line1')} />
          </Field>
          <Field id="addr_line2" label="Complément" error={errors.line2?.message}>
            <Input id="addr_line2" autoComplete="off" {...form.register('line2')} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-[8rem_1fr_6rem]">
            <Field id="addr_postal" label="Code postal" error={errors.postal_code?.message}>
              <Input id="addr_postal" autoComplete="off" {...form.register('postal_code')} />
            </Field>
            <Field id="addr_city" label="Ville" error={errors.city?.message}>
              <Input id="addr_city" autoComplete="off" {...form.register('city')} />
            </Field>
            <Field id="addr_country" label="Pays" error={errors.country_code?.message}>
              <Input id="addr_country" className="font-mono uppercase" autoComplete="off" {...form.register('country_code')} />
            </Field>
          </div>
          <Field id="addr_gln" label="GLN du lieu (facultatif)" error={errors.gln?.message} hint="Identifiant GS1, pour l'EDI">
            <Input id="addr_gln" className="font-mono" autoComplete="off" {...form.register('gln')} />
          </Field>
          <CheckRow
            checked={primary || firstOfKind}
            disabled={firstOfKind}
            onChange={(on) => form.setValue('is_primary', on)}
            title={`Adresse principale « ${ADDRESS_KINDS[kind].label} »`}
            description={
              firstOfKind
                ? "C'est la seule adresse de ce type : elle est principale d'office."
                : 'Utilisée par défaut. L’ancienne principale de ce type ne le sera plus.'
            }
          />
          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <LoaderCircle className="animate-spin" />}
              Enregistrer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

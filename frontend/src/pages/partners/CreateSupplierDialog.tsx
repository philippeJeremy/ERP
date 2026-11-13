import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { compact, type Partner } from '@/pages/partners/types'

const schema = z.object({
  name: z.string().trim().min(1, 'Raison sociale requise').max(200),
  code: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z0-9_-]{0,20}$/, 'Majuscules, chiffres, - et _ (20 max.)'),
  siret: z.string().refine((v) => /^(\d{14})?$/.test(compact(v)), '14 chiffres'),
  email: z.union([z.literal(''), z.email('Adresse e-mail invalide')]),
  phone: z.string().trim().max(30),
})
type Values = z.infer<typeof schema>

/** Création rapide : l'essentiel, puis on complète la fiche (adresses, contacts, conditions). */
export function CreateSupplierDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', code: '', siret: '', email: '', phone: '' },
  })
  const errors = form.formState.errors
  const create = useMutation({
    mutationFn: (v: Values) =>
      api<Partner>('/partners', {
        method: 'POST',
        body: Object.fromEntries(Object.entries(v).map(([k, value]) => [k, value === '' ? null : value])),
      }),
    onSuccess: async (partner) => {
      await queryClient.invalidateQueries({ queryKey: ['partners'] })
      onCreated(partner.id)
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouveau fournisseur</DialogTitle>
          <DialogDescription>
            L'essentiel suffit : vous complétez ensuite la fiche (adresses, contacts, conditions d'achat, banque).
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => create.mutate(v))} className="space-y-4" noValidate>
          <Field id="new_name" label="Raison sociale" error={errors.name?.message}>
            <Input id="new_name" autoFocus autoComplete="off" {...form.register('name')} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="new_code" label="Code" error={errors.code?.message} hint="Vide : attribué automatiquement (T00001…)">
              <Input id="new_code" className="font-mono uppercase" autoComplete="off" {...form.register('code')} />
            </Field>
            <Field id="new_siret" label="SIRET" error={errors.siret?.message}>
              <Input id="new_siret" className="font-mono" inputMode="numeric" autoComplete="off" {...form.register('siret')} />
            </Field>
            <Field id="new_email" label="E-mail" error={errors.email?.message}>
              <Input id="new_email" type="email" autoComplete="off" {...form.register('email')} />
            </Field>
            <Field id="new_phone" label="Téléphone" error={errors.phone?.message}>
              <Input id="new_phone" type="tel" autoComplete="off" {...form.register('phone')} />
            </Field>
          </div>
          <ErrorAlert error={create.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending && <LoaderCircle className="animate-spin" />}
              Créer et ouvrir la fiche
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

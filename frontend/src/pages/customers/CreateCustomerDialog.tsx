import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { compact, type CustomerKind, type Partner } from '@/pages/partners/types'

/** Création rapide d'un client : professionnel (raison sociale, SIRET) ou particulier. */
export function CreateCustomerDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<CustomerKind>('pro')
  const [v, setV] = useState({ name: '', first_name: '', siret: '', email: '', phone: '', vehicle_registration: '' })
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: e.target.value })
  const siretOk = /^(\d{14})?$/.test(compact(v.siret))
  const create = useMutation({
    mutationFn: () =>
      api<Partner>('/partners', {
        method: 'POST',
        body: {
          name: kind === 'particulier' ? v.name.trim().toUpperCase() : v.name.trim(),
          first_name: kind === 'particulier' ? v.first_name.trim() || null : null,
          siret: kind === 'pro' ? v.siret.trim() || null : null,
          email: v.email.trim() || null,
          phone: v.phone.trim() || null,
          vehicle_registration: v.vehicle_registration.trim() || null,
          is_supplier: false,
          is_customer: true,
          customer_kind: kind,
        },
      }),
    onSuccess: async (p) => {
      await queryClient.invalidateQueries({ queryKey: ['partners'] })
      onCreated(p.id)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouveau client</DialogTitle>
          <DialogDescription>L'essentiel suffit : adresses, remises et conditions se complètent sur la fiche.</DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="Type de client" className="grid grid-cols-2 gap-2">
          {(['pro', 'particulier'] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              className={cn('rounded-lg border px-3 py-2 text-sm font-medium', kind === k ? 'border-primary bg-primary/5' : 'text-muted-foreground')}
            >
              {k === 'pro' ? 'Professionnel' : 'Particulier'}
            </button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="cus_name" label={kind === 'pro' ? 'Raison sociale' : 'Nom'}>
            <Input id="cus_name" autoFocus autoComplete="off" value={v.name} onChange={set('name')} />
          </Field>
          {kind === 'pro' ? (
            <Field id="cus_siret" label="SIRET" error={siretOk ? undefined : '14 chiffres'}>
              <Input id="cus_siret" className="font-mono" inputMode="numeric" value={v.siret} onChange={set('siret')} />
            </Field>
          ) : (
            <Field id="cus_first" label="Prénom">
              <Input id="cus_first" autoComplete="off" value={v.first_name} onChange={set('first_name')} />
            </Field>
          )}
          <Field id="cus_phone" label="Téléphone">
            <Input id="cus_phone" type="tel" value={v.phone} onChange={set('phone')} />
          </Field>
          <Field id="cus_email" label="E-mail">
            <Input id="cus_email" type="email" value={v.email} onChange={set('email')} />
          </Field>
          <Field id="cus_plate" label="Immatriculation" hint="Facultatif : AB-123-CD">
            <Input id="cus_plate" className="font-mono uppercase" value={v.vehicle_registration} onChange={set('vehicle_registration')} />
          </Field>
        </div>
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!v.name.trim() || !siretOk || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <LoaderCircle className="animate-spin" />}
            Créer et ouvrir la fiche
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

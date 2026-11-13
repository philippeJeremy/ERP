import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import type { ArticleSupplier } from '@/pages/catalog/types'
import type { PartnerPage } from '@/pages/partners/types'

const schema = z.object({
  partner_id: z.string().min(1, 'Choisissez un fournisseur'),
  supplier_ref: z.string().trim().max(50),
  purchase_price: z.string().trim().refine((v) => v === '' || /^\d{1,10}([.,]\d{1,4})?$/.test(v), 'Prix invalide (ex. 65,40)'),
  is_preferred: z.boolean(),
  is_discontinued: z.boolean(),
})
type Values = z.infer<typeof schema>

/** Ajouter un fournisseur à un article, ou modifier sa référence et son prix. */
export function SupplierLinkDialog({
  articleId,
  link,
  excluded,
  onClose,
}: {
  articleId: number
  link: ArticleSupplier | null
  excluded: number[] // fournisseurs déjà liés
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const suppliers = useQuery({
    queryKey: ['partners', 'supplier-options'],
    queryFn: () => api<PartnerPage>('/partners?role=supplier&active=true&limit=200&sort=name'),
    enabled: !link,
  })
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      partner_id: link ? String(link.partner.id) : '',
      supplier_ref: link?.supplier_ref ?? '',
      purchase_price: link?.purchase_price ? String(Number(link.purchase_price)).replace('.', ',') : '',
      is_preferred: link?.is_preferred ?? false,
      is_discontinued: link?.is_discontinued ?? false,
    },
  })
  const errors = form.formState.errors
  const [preferred, discontinued] = useWatch({ control: form.control, name: ['is_preferred', 'is_discontinued'] })
  const save = useMutation({
    mutationFn: (v: Values) => {
      const price = v.purchase_price === '' ? null : v.purchase_price.replace(',', '.')
      const ref = v.supplier_ref || null
      return link
        ? api(`/catalog/article-suppliers/${link.id}`, {
            method: 'PATCH',
            body: { version: link.version, supplier_ref: ref, purchase_price: price, is_preferred: v.is_preferred, is_discontinued: v.is_discontinued },
          })
        : api(`/catalog/articles/${articleId}/suppliers`, {
            method: 'POST',
            body: { partner_id: Number(v.partner_id), supplier_ref: ref, purchase_price: price, is_preferred: v.is_preferred },
          })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['article-suppliers'] })
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
      onClose()
    },
  })
  const options = suppliers.data?.items.filter((p) => !excluded.includes(p.id)) ?? []

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{link ? `${link.partner.name}` : 'Ajouter un fournisseur'}</DialogTitle>
          <DialogDescription>Prix d'achat HT dans votre société. Les imports de tarif le mettent à jour automatiquement.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
          {!link && (
            <Field id="link_partner" label="Fournisseur" error={errors.partner_id?.message}>
              <NativeSelect id="link_partner" {...form.register('partner_id')}>
                <option value="">{suppliers.isPending ? 'Chargement…' : '— Choisir —'}</option>
                {options.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.code})
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="link_ref" label="Référence chez le fournisseur" error={errors.supplier_ref?.message}>
              <Input id="link_ref" className="font-mono" autoComplete="off" {...form.register('supplier_ref')} />
            </Field>
            <Field id="link_price" label="Prix d'achat HT (€)" error={errors.purchase_price?.message}>
              <Input id="link_price" inputMode="decimal" autoComplete="off" {...form.register('purchase_price')} />
            </Field>
          </div>
          <CheckRow
            checked={preferred}
            onChange={(on) => form.setValue('is_preferred', on)}
            title="Fournisseur préféré"
            description="Proposé en premier sur les commandes d'achat. Un seul par article."
          />
          {link && (
            <CheckRow
              checked={discontinued}
              onChange={(on) => form.setValue('is_discontinued', on)}
              title="Arrêté chez ce fournisseur"
              description="Il ne le propose plus. Un import de tarif qui le contient à nouveau le réactive."
            />
          )}
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

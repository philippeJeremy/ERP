import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { cn } from '@/lib/utils'
import { useSites } from '@/pages/inventory/hooks'
import type { PartnerPage } from '@/pages/partners/types'

/** Nouveau devis ou nouvelle commande : le client (recherche) et le dépôt d'expédition. */
export function NewSalesDocDialog({
  kind,
  customerId,
  onClose,
  onCreated,
}: {
  kind: 'quote' | 'order'
  customerId?: number
  onClose: () => void
  onCreated: (path: string) => void
}) {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const sites = useSites()
  const [site, setSite] = useState('')
  const siteValue = site || (sites.data?.[0] ? String(sites.data[0].id) : '')
  const [customer, setCustomer] = useState<{ id: number; name: string } | null>(customerId ? { id: customerId, name: '' } : null)
  const [search, setSearch] = useState('')
  const q = useDebounced(search.trim())
  const results = useQuery({
    queryKey: ['partners', company?.id, 'customer-picker', q],
    queryFn: () => api<PartnerPage>(`/partners?role=customer&active=true&limit=8&q=${encodeURIComponent(q)}`),
    enabled: !customerId,
  })
  const create = useMutation({
    mutationFn: () =>
      api<{ id: number }>(kind === 'quote' ? '/sales/quotes' : '/sales/orders', {
        method: 'POST',
        body: { customer_id: customer!.id, site_id: siteValue ? Number(siteValue) : null },
      }),
    onSuccess: (doc) => {
      void queryClient.invalidateQueries({ queryKey: [kind === 'quote' ? 'quotes' : 'orders'] })
      onCreated(kind === 'quote' ? `/ventes/devis/${doc.id}` : `/ventes/commandes/${doc.id}`)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{kind === 'quote' ? 'Nouveau devis' : 'Nouvelle commande client'}</DialogTitle>
          <DialogDescription>Les lignes se saisissent ensuite : prix du tarif, remise du client et stock disponible sont proposés.</DialogDescription>
        </DialogHeader>
        {!customerId && (
          <div className="space-y-2">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input autoFocus aria-label="Client" placeholder="Rechercher un client…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <ul className="max-h-56 divide-y overflow-auto rounded-lg border">
              {results.data?.items.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => setCustomer({ id: p.id, name: p.name })}
                    className={cn('flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-secondary/50', customer?.id === p.id && 'bg-primary/5 font-medium')}
                  >
                    <span>{p.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {p.code}
                      {p.city && ` · ${p.city}`}
                    </span>
                  </button>
                </li>
              ))}
              {results.data?.total === 0 && <li className="px-3 py-3 text-center text-sm text-muted-foreground">Aucun client</li>}
            </ul>
          </div>
        )}
        <Field id="doc_site" label="Dépôt d'expédition">
          <NativeSelect id="doc_site" value={siteValue} onChange={(e) => setSite(e.target.value)}>
            {sites.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!customer || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <LoaderCircle className="animate-spin" />}
            Créer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, LoaderCircle, MapPin, Pencil, Plus, Star, Trash2, Warehouse } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { gtinIsValid } from '@/pages/catalog/types'
import { LocationsDialog } from '@/pages/inventory/LocationsDialog'
import type { Site } from '@/pages/purchasing/types'


/** Les dépôts de la société courante : lieux de livraison des achats (et demain du stock). */
export function SitesPage() {
  const { me, company } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Site | 'new' | null>(null)
  const [locationsOf, setLocationsOf] = useState<Site | null>(null)
  const seeStock = can(me?.permissions, 'inventory:read')
  const canManage = can(me?.permissions, 'org:manage')
  const sites = useQuery({ queryKey: ['sites', company?.id], queryFn: () => api<Site[]>('/org/sites') })
  const remove = useMutation({
    mutationFn: (s: Site) => api<void>(`/org/sites/${s.id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sites'] }),
  })

  return (
    <>
      <PageHeader
        title="Dépôts"
        description={`Les lieux de ${company?.name} : adresses de livraison des commandes fournisseur, et lieux de stock (avec leurs emplacements).`}
        actions={
          canManage && (
            <Button onClick={() => setEditing('new')}>
              <Plus /> Nouveau dépôt
            </Button>
          )
        }
      />
      <ErrorAlert error={sites.error ?? remove.error} />
      {sites.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {sites.data?.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed py-12 text-center">
          <Warehouse className="size-8 text-muted-foreground/60" />
          <p className="font-medium">Aucun dépôt</p>
          <p className="text-sm text-muted-foreground">Il en faut au moins un pour passer des commandes fournisseur.</p>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sites.data?.map((s) => (
          <div key={s.id} className={`flex gap-3 rounded-xl border bg-card p-5 shadow-xs ${s.is_active ? '' : 'opacity-60'}`}>
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary">
              <Warehouse className="size-5 text-primary" />
            </span>
            <div className="min-w-0 flex-1 text-sm leading-6">
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {s.name} <span className="font-mono text-xs text-muted-foreground">{s.code}</span>
                {s.is_default && (
                  <Badge variant="accent">
                    <Star /> Par défaut
                  </Badge>
                )}
                {!s.is_active && <Badge variant="outline">Désactivé</Badge>}
              </p>
              <p className="flex gap-1 text-muted-foreground">
                <MapPin className="mt-1 size-3.5 shrink-0" />
                <span>
                  {s.address_line1}
                  {s.address_line2 && `, ${s.address_line2}`} — {s.postal_code} {s.city}
                </span>
              </p>
              {s.gln && <p className="font-mono text-xs text-muted-foreground">GLN {s.gln}</p>}
              {s.delivery_notes && <p className="mt-1 text-xs whitespace-pre-line text-muted-foreground italic">{s.delivery_notes}</p>}
              {seeStock && (
                <Button variant="outline" size="sm" className="mt-2" onClick={() => setLocationsOf(s)}>
                  <LayoutGrid /> Emplacements
                </Button>
              )}
            </div>
            {canManage && (
              <div className="flex flex-col gap-1">
                <Button variant="ghost" size="icon" aria-label={`Modifier ${s.name}`} onClick={() => setEditing(s)}>
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive"
                  aria-label={`Supprimer ${s.name}`}
                  onClick={() => window.confirm(`Supprimer le dépôt « ${s.name} » ?`) && remove.mutate(s)}
                >
                  <Trash2 />
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
      {editing && <SiteDialog site={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {locationsOf && <LocationsDialog site={locationsOf} onClose={() => setLocationsOf(null)} />}
    </>
  )
}

function SiteDialog({ site, onClose }: { site: Site | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    code: site?.code ?? '',
    name: site?.name ?? '',
    address_line1: site?.address_line1 ?? '',
    address_line2: site?.address_line2 ?? '',
    postal_code: site?.postal_code ?? '',
    city: site?.city ?? '',
    country_code: site?.country_code ?? 'FR',
    phone: site?.phone ?? '',
    delivery_notes: site?.delivery_notes ?? '',
    gln: site?.gln ?? '',
    is_default: site?.is_default ?? false,
    is_active: site?.is_active ?? true,
  })
  type Key = keyof typeof form
  const set = (k: Key, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }))
  const glnError = form.gln.trim() && !(form.gln.replace(/\s/g, '').length === 13 && gtinIsValid(form.gln.replace(/\s/g, ''))) ? 'GLN invalide (13 chiffres, clé GS1)' : undefined
  const save = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() || null : v]))
      body.code = form.code.trim().toUpperCase()
      body.country_code = form.country_code.trim().toUpperCase() || 'FR'
      return site ? api(`/org/sites/${site.id}`, { method: 'PUT', body }) : api('/org/sites', { method: 'POST', body })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sites'] })
      onClose()
    },
  })
  const field = (k: Key, label: string, extra?: { className?: string; mono?: boolean; hint?: string; error?: string; placeholder?: string }) => (
    <div className={extra?.className}>
      <Field id={`site_${k}`} label={label} hint={extra?.hint} error={extra?.error}>
        <Input id={`site_${k}`} autoComplete="off" placeholder={extra?.placeholder} className={extra?.mono ? 'font-mono uppercase' : undefined} value={form[k] as string} onChange={(e) => set(k, e.target.value)} />
      </Field>
    </div>
  )
  const valid = form.code.trim() && form.name.trim() && form.address_line1.trim() && form.postal_code.trim() && form.city.trim() && !glnError

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{site ? `Modifier ${site.name}` : 'Nouveau dépôt'}</DialogTitle>
          <DialogDescription>Cette adresse figure sur les bons de commande comme lieu de livraison.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-6">
          {field('code', 'Code', { className: 'sm:col-span-2', mono: true, placeholder: 'LYON' })}
          {field('name', 'Nom', { className: 'sm:col-span-4', placeholder: 'Entrepôt de Lyon' })}
          {field('address_line1', 'Adresse', { className: 'sm:col-span-6' })}
          {field('address_line2', 'Complément', { className: 'sm:col-span-6' })}
          {field('postal_code', 'Code postal', { className: 'sm:col-span-2' })}
          {field('city', 'Ville', { className: 'sm:col-span-3' })}
          {field('country_code', 'Pays', { className: 'sm:col-span-1', mono: true })}
          {field('phone', 'Téléphone de réception', { className: 'sm:col-span-3' })}
          {field('gln', 'GLN', { className: 'sm:col-span-3', mono: true, error: glnError, hint: 'Identifiant GS1 du lieu, pour l’EDI (facultatif)' })}
          <div className="sm:col-span-6">
            <Field id="site_notes" label="Consignes de livraison" hint="Imprimées sur le bon de commande : horaires, quai, accès poids lourds…">
              <Textarea id="site_notes" rows={2} value={form.delivery_notes} onChange={(e) => set('delivery_notes', e.target.value)} />
            </Field>
          </div>
          <CheckRow className="sm:col-span-3" checked={form.is_default} onChange={(on) => set('is_default', on)} title="Dépôt par défaut" description="Proposé sur les nouvelles commandes." />
          <CheckRow className="sm:col-span-3" checked={form.is_active} onChange={(on) => set('is_active', on)} title="Actif" description="Désactivé : plus proposé." />
        </div>
        <ErrorAlert error={save.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <LoaderCircle className="animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

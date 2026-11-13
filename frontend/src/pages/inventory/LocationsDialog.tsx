import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Pencil, Plus, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useLocations } from '@/pages/inventory/hooks'
import type { Location } from '@/pages/inventory/types'
import type { Site } from '@/pages/purchasing/types'

/** Les emplacements d'un dépôt : allée-rack-niveau (A-01-2), quai, zone d'expédition… */
export function LocationsDialog({ site, onClose }: { site: Site; onClose: () => void }) {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const canManage = can(me?.permissions, 'inventory:manage')
  const locations = useLocations(site.id, false)
  const [editing, setEditing] = useState<Location | 'new' | null>(null)
  const [form, setForm] = useState({ code: '', name: '', is_default: false, is_active: true })
  const start = (l: Location | 'new') => {
    setEditing(l)
    setForm(l === 'new' ? { code: '', name: '', is_default: false, is_active: true } : { code: l.code, name: l.name ?? '', is_default: l.is_default, is_active: l.is_active })
  }
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['locations'] })
  const save = useMutation({
    mutationFn: () => {
      const body = { code: form.code.trim(), name: form.name.trim() || null, is_default: form.is_default, is_active: form.is_active }
      return editing === 'new' ? api(`/inventory/sites/${site.id}/locations`, { method: 'POST', body }) : api(`/inventory/locations/${(editing as Location).id}`, { method: 'PUT', body })
    },
    onSuccess: async () => {
      await refresh()
      setEditing(null)
    },
  })
  const remove = useMutation({
    mutationFn: (l: Location) => api<void>(`/inventory/locations/${l.id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Emplacements — {site.name}</DialogTitle>
          <DialogDescription>Où ranger le stock dans le dépôt. Les réceptions arrivent sur l'emplacement par défaut, sauf choix contraire.</DialogDescription>
        </DialogHeader>
        <ErrorAlert error={locations.error ?? remove.error} />
        <ul className="max-h-80 divide-y overflow-auto rounded-lg border">
          {locations.data?.map((l) => (
            <li key={l.id} className={`flex items-center gap-3 px-3 py-2 text-sm ${l.is_active ? '' : 'opacity-60'}`}>
              <span className="w-28 font-mono font-medium">{l.code}</span>
              <span className="flex-1 text-muted-foreground">{l.name}</span>
              {l.is_default && (
                <Badge variant="accent">
                  <Star /> Par défaut
                </Badge>
              )}
              {!l.is_active && <Badge variant="outline">Désactivé</Badge>}
              {canManage && (
                <>
                  <Button variant="ghost" size="icon" aria-label={`Modifier ${l.code}`} onClick={() => start(l)}>
                    <Pencil />
                  </Button>
                  {!l.is_default && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      aria-label={`Supprimer ${l.code}`}
                      onClick={() => window.confirm(`Supprimer l'emplacement ${l.code} ?`) && remove.mutate(l)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </>
              )}
            </li>
          ))}
          {locations.isPending && (
            <li className="flex justify-center py-4">
              <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
            </li>
          )}
        </ul>
        {canManage && !editing && (
          <Button variant="outline" className="w-fit" onClick={() => start('new')}>
            <Plus /> Nouvel emplacement
          </Button>
        )}
        {editing && (
          <div className="space-y-3 rounded-lg border bg-secondary/30 p-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <Input aria-label="Code de l'emplacement" placeholder="A-01-2" className="font-mono uppercase" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} autoFocus />
              <Input aria-label="Libellé" placeholder="Allée A, rack 1, niveau 2" className="sm:col-span-2" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="flex flex-wrap gap-4">
              <CheckRow title="Emplacement par défaut (réceptions)" checked={form.is_default} onChange={(v) => setForm({ ...form, is_default: v })} />
              <CheckRow title="Actif" checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} />
            </div>
            <ErrorAlert error={save.error} />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>
                Annuler
              </Button>
              <Button disabled={!form.code.trim() || save.isPending} onClick={() => save.mutate()}>
                {save.isPending && <LoaderCircle className="animate-spin" />}
                Enregistrer
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardList, LoaderCircle, Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { useLocations, useSites } from '@/pages/inventory/hooks'
import { COUNT_STATUSES, type Count, type CountListItem } from '@/pages/inventory/types'

const PAGE_SIZE = 25

export function CountsTab() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const status = params.get('statut') ?? ''
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  if (status) query.set('status', status)
  const list = useQuery({
    queryKey: ['counts', company?.id, query.toString()],
    queryFn: () => api<{ items: CountListItem[]; total: number }>(`/inventory/counts?${query}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <NativeSelect aria-label="Statut" className="w-40" value={status} onChange={(e) => update({ statut: e.target.value, page: null })}>
          <option value="">Tous les statuts</option>
          {Object.entries(COUNT_STATUSES).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </NativeSelect>
        <p className="flex-1 text-sm text-muted-foreground">À l'ouverture, le stock théorique est photographié ; à la validation, chaque écart devient un mouvement.</p>
        {can(me?.permissions, 'inventory:manage') && (
          <Button onClick={() => setCreating(true)}>
            <Plus /> Nouvel inventaire
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N°</th>
              <th className="px-4 py-2.5 font-medium">Dépôt</th>
              <th className="px-4 py-2.5 font-medium">Ouvert le</th>
              <th className="px-4 py-2.5 font-medium">Avancement</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((c) => (
              <tr key={c.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/stock/inventaires/${c.id}`)}>
                <td className="px-4 py-3 font-mono text-xs">{c.number}</td>
                <td className="px-4 py-3">
                  {c.site.name}
                  {c.location && <span className="ml-1 font-mono text-xs text-muted-foreground">· {c.location.code}</span>}
                </td>
                <td className="px-4 py-3 text-muted-foreground">{formatDateTime(c.created_at)}</td>
                <td className="px-4 py-3">
                  <span className="tabular-nums">
                    {c.counted_count} / {c.line_count}
                  </span>
                  <div className="mt-1 h-1 w-24 overflow-hidden rounded bg-secondary">
                    <div className="h-full bg-emerald-600" style={{ width: `${c.line_count ? (c.counted_count / c.line_count) * 100 : 0}%` }} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge variant={COUNT_STATUSES[c.status].variant}>{COUNT_STATUSES[c.status].label}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <ClipboardList className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun inventaire</p>
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['inventaire', 'inventaires']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <NewCountDialog onClose={() => setCreating(false)} onCreated={(c) => navigate(`/stock/inventaires/${c.id}`)} />}
    </>
  )
}

function NewCountDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Count) => void }) {
  const queryClient = useQueryClient()
  const sites = useSites()
  const [site, setSite] = useState('')
  const siteValue = site || (sites.data?.[0] ? String(sites.data[0].id) : '')
  const locations = useLocations(siteValue ? Number(siteValue) : null)
  const [location, setLocation] = useState('')
  const [note, setNote] = useState('')
  const create = useMutation({
    mutationFn: () => api<Count>('/inventory/counts', { method: 'POST', body: { site_id: Number(siteValue), location_id: location ? Number(location) : null, note: note.trim() || null } }),
    onSuccess: (c) => {
      void queryClient.invalidateQueries({ queryKey: ['counts'] })
      onCreated(c)
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nouvel inventaire</DialogTitle>
          <DialogDescription>Tout un dépôt (inventaire annuel) ou un seul emplacement (inventaire tournant).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="cnt_site" label="Dépôt">
            <NativeSelect
              id="cnt_site"
              value={siteValue}
              onChange={(e) => {
                setSite(e.target.value)
                setLocation('')
              }}
            >
              {sites.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="cnt_location" label="Emplacement">
            <NativeSelect id="cnt_location" value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">Tout le dépôt</option>
              {locations.data?.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.code}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        <Field id="cnt_note" label="Note">
          <Textarea id="cnt_note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorAlert error={create.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!siteValue || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <LoaderCircle className="animate-spin" />}
            Ouvrir l'inventaire
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

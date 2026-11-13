import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowRight, ArrowRightLeft, LoaderCircle, Plus } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert } from '@/components/ui/field'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { formatDate } from '@/pages/purchasing/types'
import { MovesTable } from '@/pages/inventory/parts'
import { TransferDialog } from '@/pages/inventory/TransferDialog'
import { fmtQty, type Transfer, type TransferListItem } from '@/pages/inventory/types'

const PAGE_SIZE = 25

export function TransfersTab() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const opened = params.get('transfert')
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  const list = useQuery({
    queryKey: ['transfers', company?.id, query.toString()],
    queryFn: () => api<{ items: TransferListItem[]; total: number }>(`/inventory/transfers?${query}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Un transfert est immédiat : le stock sort du dépôt de départ et entre dans celui d'arrivée, au même coût moyen.</p>
        {can(me?.permissions, 'inventory:manage') && (
          <Button onClick={() => setCreating(true)}>
            <Plus /> Nouveau transfert
          </Button>
        )}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">N°</th>
              <th className="px-4 py-2.5 font-medium">Date</th>
              <th className="px-4 py-2.5 font-medium">Trajet</th>
              <th className="px-4 py-2.5 text-right font-medium">Lignes</th>
              <th className="px-4 py-2.5 text-right font-medium">Quantité</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Note</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((t) => (
              <tr key={t.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => update({ transfert: String(t.id) })}>
                <td className="px-4 py-3 font-mono text-xs">{t.number}</td>
                <td className="px-4 py-3">{formatDate(t.transferred_on)}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5">
                    {t.from_site.name} <ArrowRight className="size-3.5 text-muted-foreground" /> {t.to_site.name}
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{t.line_count}</td>
                <td className="px-4 py-3 text-right font-medium tabular-nums">{fmtQty(t.total_quantity)}</td>
                <td className="hidden max-w-60 truncate px-4 py-3 text-muted-foreground md:table-cell">{t.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <ArrowRightLeft className="size-8 text-muted-foreground/60" />
            <p className="font-medium">Aucun transfert</p>
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['transfert', 'transferts']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <TransferDialog onClose={() => setCreating(false)} onCreated={(t) => update({ transfert: String(t.id) })} />}
      {opened && <TransferDetail id={Number(opened)} onClose={() => update({ transfert: null })} />}
    </>
  )
}

function TransferDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { company } = useAuth()
  const transfer = useQuery({ queryKey: ['transfers', company?.id, 'detail', id], queryFn: () => api<Transfer>(`/inventory/transfers/${id}`) })
  const t = transfer.data
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Transfert {t?.number}</DialogTitle>
          <DialogDescription>
            {t ? `${t.from_site.name} → ${t.to_site.name}, le ${formatDate(t.transferred_on)}${t.note ? ` — ${t.note}` : ''}` : 'Chargement…'}
          </DialogDescription>
        </DialogHeader>
        <ErrorAlert error={transfer.error} />
        {t && (
          <div className="max-h-[60vh] overflow-auto rounded-lg border">
            <MovesTable moves={t.moves} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { LoaderCircle, Plus, Search, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Pagination } from '@/components/data/Pagination'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import { useDebounced } from '@/lib/useDebounced'
import { useUrlState } from '@/lib/useUrlState'
import { CreateCustomerDialog } from '@/pages/customers/CreateCustomerDialog'
import type { PartnerPage } from '@/pages/partners/types'

const PAGE_SIZE = 25

export function CustomersPage() {
  const { me, company } = useAuth()
  const navigate = useNavigate()
  const [params, update] = useUrlState()
  const [creating, setCreating] = useState(false)
  const page = Math.max(0, Number(params.get('page') ?? 1) - 1)
  const status = params.get('statut') ?? 'actifs'
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())
  useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q, page: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  const query = new URLSearchParams({ role: 'customer', limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE), sort: 'name' })
  if (status !== 'tous') query.set('active', String(status === 'actifs'))
  if (q) query.set('q', q)
  const list = useQuery({
    queryKey: ['partners', company?.id, query.toString()],
    queryFn: () => api<PartnerPage>(`/partners?${query}`),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <PageHeader
        title="Clients"
        description={`Les clients de ${company?.name} : garages, flottes et particuliers.`}
        actions={
          can(me?.permissions, 'partners:manage') && (
            <Button onClick={() => setCreating(true)}>
              <Plus /> Nouveau client
            </Button>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label="Rechercher un client" placeholder="Nom, code, SIRET, ville…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Statut" className="w-36" value={status} onChange={(e) => update({ statut: e.target.value === 'actifs' ? null : e.target.value, page: null })}>
          <option value="actifs">Actifs</option>
          <option value="inactifs">Désactivés</option>
          <option value="tous">Tous</option>
        </NativeSelect>
        {list.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
      </div>
      <ErrorAlert error={list.error} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Code</th>
              <th className="px-4 py-2.5 font-medium">Client</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Ville</th>
              <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Coordonnées</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.data?.items.map((p) => (
              <tr key={p.id} className="cursor-pointer hover:bg-secondary/40" onClick={() => navigate(`/clients/${p.id}`)}>
                <td className="px-4 py-3 font-mono text-xs">{p.code}</td>
                <td className="px-4 py-3">
                  <p className="font-medium">{p.name}</p>
                  {p.siret && <p className="font-mono text-xs text-muted-foreground">{p.siret}</p>}
                </td>
                <td className="hidden px-4 py-3 md:table-cell">{p.city ?? '—'}</td>
                <td className="hidden px-4 py-3 text-xs text-muted-foreground lg:table-cell">
                  {p.phone && <p>{p.phone}</p>}
                  {p.email && <p>{p.email}</p>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {p.is_active ? <Badge variant="success">Actif</Badge> : <Badge variant="outline">Désactivé</Badge>}
                    {p.is_supplier && <Badge variant="secondary">Aussi fournisseur</Badge>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.total === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <Users className="size-8 text-muted-foreground/60" />
            <p className="font-medium">{q ? 'Aucun client ne correspond' : 'Aucun client pour le moment'}</p>
          </div>
        )}
        {list.isPending && (
          <div className="flex justify-center py-12">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} noun={['client', 'clients']} onPage={(p) => update({ page: p ? String(p + 1) : null })} />
      {creating && <CreateCustomerDialog onClose={() => setCreating(false)} onCreated={(id) => navigate(`/clients/${id}`)} />}
    </>
  )
}

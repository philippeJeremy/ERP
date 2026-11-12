import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { can } from '@/lib/permissions'
import type { Company } from '@/lib/types'
import { CompanyDialog } from '@/pages/admin/CompanyDialog'

export function CompaniesPage() {
  const { me, company: current } = useAuth()
  const isSuperuser = !!me?.user.is_superuser
  const canManageCurrent = can(me?.permissions, 'org:manage')
  const [editing, setEditing] = useState<Company | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Company | null>(null)

  // Même clé que la liste du sélecteur de société : une seule requête, un seul cache.
  const companies = useQuery({
    queryKey: ['companies'],
    queryFn: () => api<Company[]>('/org/companies', { withCompany: false }),
  })
  // Un super-administrateur modifie toutes les sociétés ; les autres, seulement la
  // société courante, s'ils en ont le droit (même règle que l'API).
  const canEdit = (c: Company) => isSuperuser || (c.id === current?.id && canManageCurrent)

  return (
    <>
      <PageHeader
        title="Sociétés"
        description={
          isSuperuser
            ? 'Les entités juridiques du groupe. Chacune a sa numérotation, ses utilisateurs et ses données.'
            : 'Les sociétés auxquelles vous avez accès.'
        }
        actions={
          isSuperuser && (
            <Button onClick={() => setEditing('new')}>
              <Plus /> Nouvelle société
            </Button>
          )
        }
      />
      <ErrorAlert error={companies.error} />
      {companies.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}

      <div className="overflow-x-auto rounded-xl border bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Société</th>
              <th className="hidden px-4 py-2.5 font-medium sm:table-cell">SIREN</th>
              <th className="hidden px-4 py-2.5 font-medium md:table-cell">Ville</th>
              <th className="px-4 py-2.5 font-medium">Statut</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {companies.data?.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-accent/20 text-xs font-semibold text-accent-foreground">
                      {c.code.slice(0, 2)}
                    </span>
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 font-medium">
                        {c.name}
                        {c.id === current?.id && <Badge variant="secondary">Société courante</Badge>}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        <span className="font-mono">{c.code}</span>
                        {c.legal_form && ` · ${c.legal_form}`}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="hidden px-4 py-3 font-mono text-xs sm:table-cell">{c.siren ?? '—'}</td>
                <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{c.city ?? '—'}</td>
                <td className="px-4 py-3">
                  {c.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="outline">Désactivée</Badge>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {canEdit(c) && (
                      <Button variant="ghost" size="icon" onClick={() => setEditing(c)} aria-label={`Modifier ${c.name}`} title="Modifier">
                        <Pencil />
                      </Button>
                    )}
                    {isSuperuser && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleting(c)}
                        aria-label={`Supprimer ${c.name}`}
                        title="Supprimer"
                      >
                        <Trash2 />
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <CompanyDialog
          key={editing === 'new' ? 'new' : editing.id}
          company={editing === 'new' ? null : editing}
          isSuperuser={isSuperuser}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && <DeleteCompanyDialog company={deleting} onClose={() => setDeleting(null)} />}
    </>
  )
}

function DeleteCompanyDialog({ company, onClose }: { company: Company; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState('')
  const remove = useMutation({
    mutationFn: () => api<void>(`/org/companies/${company.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['companies'] })
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      onClose()
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Supprimer « {company.name} » ?</DialogTitle>
          <DialogDescription>
            Action définitive, réservée aux sociétés vides (créées par erreur). Sa numérotation et les accès de ses
            utilisateurs sont supprimés ; les comptes eux-mêmes sont conservés. Une société qui contient des données
            ne peut pas être supprimée : désactivez-la.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (typed === company.code) remove.mutate()
          }}
        >
          {/* Retaper le code : impossible de supprimer la mauvaise société d'un clic distrait. */}
          <Field id="confirm_code" label={`Pour confirmer, saisissez le code ${company.code}`}>
            <Input id="confirm_code" className="font-mono" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </Field>
          <ErrorAlert error={remove.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" variant="destructive" disabled={typed !== company.code || remove.isPending}>
              {remove.isPending && <LoaderCircle className="animate-spin" />}
              Supprimer la société
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

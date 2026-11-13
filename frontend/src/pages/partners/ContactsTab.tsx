import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, Mail, Pencil, Phone, Plus, Smartphone, Star, Trash2, UserRound } from 'lucide-react'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { initials } from '@/lib/format'
import type { Partner, PartnerContact } from '@/pages/partners/types'

const fullName = (c: PartnerContact) => [c.first_name, c.last_name].filter(Boolean).join(' ')

export function ContactsTab({ partner, readOnly }: { partner: Partner; readOnly: boolean }) {
  const [editing, setEditing] = useState<PartnerContact | 'new' | null>(null)
  const queryClient = useQueryClient()
  const remove = useMutation({
    mutationFn: (c: PartnerContact) => api<void>(`/partners/${partner.id}/contacts/${c.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['partner'] })
      void queryClient.invalidateQueries({ queryKey: ['partners'] })
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Les personnes à joindre : commercial, ADV, comptabilité… L'interlocuteur principal est affiché dans la liste.
        </p>
        {!readOnly && (
          <Button onClick={() => setEditing('new')}>
            <Plus /> Ajouter un contact
          </Button>
        )}
      </div>
      <ErrorAlert error={remove.error} />

      {partner.contacts.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
          <UserRound className="size-6" />
          Aucun contact.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {partner.contacts.map((c) => (
          <div key={c.id} className="flex gap-3 rounded-xl border bg-card p-4 shadow-xs">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold">
              {initials(fullName(c))}
            </span>
            <div className="min-w-0 flex-1 space-y-1 text-sm">
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {fullName(c)}
                {c.is_primary && (
                  <Badge variant="accent">
                    <Star /> Principal
                  </Badge>
                )}
              </p>
              {c.job_title && <p className="text-xs text-muted-foreground">{c.job_title}</p>}
              <div className="space-y-0.5 pt-1 text-xs">
                {c.email && (
                  <a href={`mailto:${c.email}`} className="flex items-center gap-1.5 truncate text-primary hover:underline">
                    <Mail className="size-3.5 shrink-0" /> {c.email}
                  </a>
                )}
                {c.phone && (
                  <a href={`tel:${c.phone}`} className="flex items-center gap-1.5 hover:underline">
                    <Phone className="size-3.5 shrink-0" /> {c.phone}
                  </a>
                )}
                {c.mobile && (
                  <a href={`tel:${c.mobile}`} className="flex items-center gap-1.5 hover:underline">
                    <Smartphone className="size-3.5 shrink-0" /> {c.mobile}
                  </a>
                )}
              </div>
              {c.notes && <p className="pt-1 text-xs whitespace-pre-line text-muted-foreground">{c.notes}</p>}
            </div>
            {!readOnly && (
              <div className="flex flex-col gap-1">
                <Button variant="ghost" size="icon" title="Modifier" aria-label={`Modifier ${fullName(c)}`} onClick={() => setEditing(c)}>
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive"
                  title="Supprimer"
                  aria-label={`Supprimer ${fullName(c)}`}
                  disabled={remove.isPending}
                  onClick={() => window.confirm(`Supprimer le contact « ${fullName(c)} » ?`) && remove.mutate(c)}
                >
                  <Trash2 />
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>

      {editing && <ContactDialog partner={partner} contact={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

const schema = z.object({
  first_name: z.string().trim().max(100),
  last_name: z.string().trim().min(1, 'Nom requis').max(100),
  job_title: z.string().trim().max(100),
  email: z.union([z.literal(''), z.email('Adresse e-mail invalide')]),
  phone: z.string().trim().max(30),
  mobile: z.string().trim().max(30),
  notes: z.string(),
  is_primary: z.boolean(),
})
type Values = z.infer<typeof schema>

function ContactDialog({ partner, contact, onClose }: { partner: Partner; contact: PartnerContact | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const first = partner.contacts.length === 0 || (partner.contacts.length === 1 && !!contact)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      first_name: contact?.first_name ?? '',
      last_name: contact?.last_name ?? '',
      job_title: contact?.job_title ?? '',
      email: contact?.email ?? '',
      phone: contact?.phone ?? '',
      mobile: contact?.mobile ?? '',
      notes: contact?.notes ?? '',
      is_primary: contact?.is_primary ?? false,
    },
  })
  const errors = form.formState.errors
  const primary = useWatch({ control: form.control, name: 'is_primary' })
  const save = useMutation({
    mutationFn: (v: Values) => {
      const body = Object.fromEntries(Object.entries(v).map(([k, value]) => [k, value === '' ? null : value]))
      return contact
        ? api(`/partners/${partner.id}/contacts/${contact.id}`, { method: 'PUT', body })
        : api(`/partners/${partner.id}/contacts`, { method: 'POST', body })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['partner'] })
      void queryClient.invalidateQueries({ queryKey: ['partners'] })
      onClose()
    },
  })
  const field = (name: Exclude<keyof Values, 'is_primary' | 'notes'>, label: string, type?: string) => (
    <Field id={`ct_${name}`} label={label} error={errors[name]?.message}>
      <Input id={`ct_${name}`} type={type} autoComplete="off" {...form.register(name)} />
    </Field>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{contact ? 'Modifier le contact' : 'Nouveau contact'}</DialogTitle>
          <DialogDescription>{partner.name}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            {field('first_name', 'Prénom')}
            {field('last_name', 'Nom')}
            <div className="sm:col-span-2">{field('job_title', 'Fonction')}</div>
            <div className="sm:col-span-2">{field('email', 'E-mail', 'email')}</div>
            {field('phone', 'Téléphone fixe', 'tel')}
            {field('mobile', 'Mobile', 'tel')}
          </div>
          <Field id="ct_notes" label="Notes">
            <Textarea id="ct_notes" rows={2} {...form.register('notes')} />
          </Field>
          <CheckRow
            checked={primary || first}
            disabled={first}
            onChange={(on) => form.setValue('is_primary', on)}
            title="Interlocuteur principal"
            description={first ? "C'est le seul contact : il est principal d'office." : "L'ancien interlocuteur principal ne le sera plus."}
          />
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

import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle, Mail, Paperclip, Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/native-select'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { MAIL_STATUSES, parseEmails, type EmailDraft } from '@/pages/mail/types'

/** Fenêtre d'envoi par mail d'un document : tout est pré-rempli par le modèle de la
 * société et modifiable. Le document est joint en PDF. */
export function EmailDialog<T>({ title, path, onSent, onClose }: { title: string; path: string; onSent: (result: T) => void; onClose: () => void }) {
  const { company } = useAuth()
  const draft = useQuery({ queryKey: ['email-draft', company?.id, path], queryFn: () => api<EmailDraft>(path), gcTime: 0 })
  const [edits, setEdits] = useState<{ to?: string; cc?: string; subject?: string; body?: string }>({})
  const d = draft.data
  const to = edits.to ?? d?.to.join(', ') ?? ''
  const cc = edits.cc ?? d?.cc.join(', ') ?? ''
  const subject = edits.subject ?? d?.subject ?? ''
  const body = edits.body ?? d?.body ?? ''
  const toList = parseEmails(to)
  const ccList = parseEmails(cc)
  const addTo = (email: string) => {
    const current = parseEmails(to) ?? []
    if (!current.includes(email)) setEdits({ ...edits, to: [...current, email].join(', ') })
  }
  const send = useMutation({
    mutationFn: () => api<T>(path, { method: 'POST', body: { to: toList, cc: ccList ?? [], subject: subject.trim(), body } }),
    onSuccess: (result) => {
      onSent(result)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="size-5" /> {title}
          </DialogTitle>
          <DialogDescription>Message pré-rempli d'après le modèle de la société : modifiez-le librement avant l'envoi.</DialogDescription>
        </DialogHeader>
        <ErrorAlert error={draft.error} />
        {draft.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
        {d && (
          <div className="space-y-4">
            {!d.smtp_ready && (
              <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-900">
                L'envoi de mails n'est pas encore configuré pour cette société.{' '}
                <Link to="/admin/messagerie" className="font-medium underline">
                  Régler le serveur d'envoi
                </Link>
              </p>
            )}
            <Field id="mail_to" label="À" error={to && !toList ? 'Adresse invalide' : undefined}>
              <Input id="mail_to" value={to} placeholder="adresse@client.fr, autre@client.fr" onChange={(e) => setEdits({ ...edits, to: e.target.value })} />
            </Field>
            {d.suggestions.length > 0 && (
              <div className="-mt-2 flex flex-wrap gap-1.5">
                {d.suggestions.map((s) => (
                  <button key={s.email} type="button" onClick={() => addTo(s.email)} className="rounded-full border px-2.5 py-0.5 text-xs hover:bg-secondary" title={s.email}>
                    + {s.label}
                  </button>
                ))}
              </div>
            )}
            <Field id="mail_cc" label="Copie" error={cc && !ccList ? 'Adresse invalide' : undefined}>
              <Input id="mail_cc" value={cc} onChange={(e) => setEdits({ ...edits, cc: e.target.value })} />
            </Field>
            <Field id="mail_subject" label="Objet">
              <Input id="mail_subject" value={subject} onChange={(e) => setEdits({ ...edits, subject: e.target.value })} />
            </Field>
            <Field id="mail_body" label="Message">
              <Textarea id="mail_body" rows={10} value={body} onChange={(e) => setEdits({ ...edits, body: e.target.value })} />
            </Field>
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Paperclip className="size-4" />
              {d.attachments.map((a) => (
                <Badge key={a} variant="secondary">
                  {a}
                </Badge>
              ))}
            </p>
            {d.history.length > 0 && (
              <div className="rounded-lg border p-3">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Déjà envoyé</p>
                <ul className="space-y-1 text-xs">
                  {d.history.slice(0, 5).map((m) => (
                    <li key={m.id} className="flex flex-wrap items-center gap-2">
                      <span>{formatDateTime(m.sent_at ?? m.created_at)}</span>
                      <span className="text-muted-foreground">à {m.to_addrs.replaceAll(',', ', ')}</span>
                      <Badge variant={MAIL_STATUSES[m.status].variant}>{MAIL_STATUSES[m.status].label}</Badge>
                      {m.error && <span className="text-destructive">{m.error}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        <ErrorAlert error={send.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={!d?.smtp_ready || !toList?.length || ccList === null || !subject.trim() || !body.trim() || send.isPending} onClick={() => send.mutate()}>
            {send.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
            Envoyer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

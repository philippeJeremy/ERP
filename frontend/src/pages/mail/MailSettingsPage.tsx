import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FileText, LoaderCircle, RotateCcw, RotateCw, Save, Send } from 'lucide-react'
import { useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/layout/PageHeader'
import { Pagination } from '@/components/data/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CheckRow, ErrorAlert, Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, Textarea } from '@/components/ui/native-select'
import { api, openFile } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { can } from '@/lib/permissions'
import { useUrlState } from '@/lib/useUrlState'
import { cn } from '@/lib/utils'
import { MAIL_STATUSES, type MailMessage, type MailTemplate, type SmtpSettings } from '@/pages/mail/types'

const TABS = [
  { id: 'serveur', label: "Serveur d'envoi", permission: 'mail:settings' },
  { id: 'modeles', label: 'Modèles de message', permission: 'mail:settings' },
  { id: 'historique', label: 'Historique des envois', permission: 'mail:read' },
] as const

/** Réglages de la messagerie de la société : serveur SMTP, modèles et journal des envois. */
export function MailSettingsPage() {
  const { me, company } = useAuth()
  const [params, update] = useUrlState()
  const tabs = TABS.filter((t) => can(me?.permissions, t.permission))
  const tab = tabs.find((t) => t.id === params.get('vue'))?.id ?? tabs[0]?.id
  if (!tab) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Accès refusé</CardTitle>
          <CardDescription>Vous n'avez pas le droit de voir la messagerie.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <>
      <PageHeader title="Messagerie" description={`Envoi des devis, factures, relances et commandes de ${company?.name} par e-mail.`} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => update({ vue: t.id, page: null })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap',
              tab === t.id ? 'border-accent text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'serveur' && <SmtpTab />}
      {tab === 'modeles' && <TemplatesTab />}
      {tab === 'historique' && <HistoryTab />}
    </>
  )
}

function SmtpTab() {
  const { company } = useAuth()
  const smtp = useQuery({ queryKey: ['mail-smtp', company?.id], queryFn: () => api<SmtpSettings>('/mail/smtp') })
  return (
    <>
      <ErrorAlert error={smtp.error} />
      {smtp.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {smtp.data && <SmtpForm key={company?.id} initial={smtp.data} />}
    </>
  )
}

function SmtpForm({ initial }: { initial: SmtpSettings }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    enabled: initial.configured ? initial.enabled : true,
    host: initial.host ?? '',
    port: String(initial.port),
    security: initial.security,
    username: initial.username ?? '',
    password: '',
    from_email: initial.from_email ?? '',
    from_name: initial.from_name ?? '',
    reply_to: initial.reply_to ?? '',
    bcc: initial.bcc ?? '',
  })
  const [testTo, setTestTo] = useState('')
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const save = useMutation({
    mutationFn: () =>
      api<SmtpSettings>('/mail/smtp', {
        method: 'PUT',
        body: {
          ...form,
          port: Number(form.port),
          username: form.username.trim() || null,
          password: form.password || null,
          from_name: form.from_name.trim() || null,
          reply_to: form.reply_to.trim() || null,
          bcc: form.bcc.trim() || null,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mail-smtp'] })
      set({ password: '' })
    },
  })
  const test = useMutation({
    mutationFn: () => api<MailMessage>('/mail/smtp/test', { method: 'POST', body: { to: testTo.trim() } }),
  })
  const onSecurity = (security: SmtpSettings['security']) => {
    const defaults = { starttls: '587', ssl: '465', none: '25' }
    set({ security, port: Object.values(defaults).includes(form.port) ? defaults[security] : form.port })
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <form
        className="space-y-4 rounded-xl border bg-card p-5 shadow-xs"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <CheckRow checked={form.enabled} onChange={(enabled) => set({ enabled })} title="Envoi de mails activé" description="Décochez pour suspendre tous les envois de la société." />
        <div className="grid gap-4 sm:grid-cols-[1fr_7rem_10rem]">
          <Field id="smtp_host" label="Serveur SMTP">
            <Input id="smtp_host" required value={form.host} placeholder="smtp.example.com" onChange={(e) => set({ host: e.target.value.trim() })} />
          </Field>
          <Field id="smtp_port" label="Port">
            <Input id="smtp_port" required type="number" min={1} max={65535} value={form.port} onChange={(e) => set({ port: e.target.value })} />
          </Field>
          <Field id="smtp_security" label="Sécurité">
            <NativeSelect id="smtp_security" value={form.security} onChange={(e) => onSecurity(e.target.value as SmtpSettings['security'])}>
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL/TLS</option>
              <option value="none">Aucune</option>
            </NativeSelect>
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="smtp_user" label="Identifiant">
            <Input id="smtp_user" autoComplete="off" value={form.username} onChange={(e) => set({ username: e.target.value })} />
          </Field>
          <Field id="smtp_password" label="Mot de passe" hint={!form.username.trim() ? "Sans identifiant, l'envoi se fait sans authentification." : initial.has_password ? 'Enregistré (chiffré). Laissez vide pour le conserver.' : 'Stocké chiffré, jamais réaffiché.'}>
            <Input id="smtp_password" disabled={!form.username.trim()} type="password" autoComplete="new-password" value={form.password} placeholder={initial.has_password ? '••••••••' : ''} onChange={(e) => set({ password: e.target.value })} />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="smtp_from" label="Adresse d'expédition">
            <Input id="smtp_from" required type="email" value={form.from_email} placeholder="facturation@example.com" onChange={(e) => set({ from_email: e.target.value })} />
          </Field>
          <Field id="smtp_from_name" label="Nom affiché" hint="Par défaut : le nom de la société.">
            <Input id="smtp_from_name" value={form.from_name} onChange={(e) => set({ from_name: e.target.value })} />
          </Field>
          <Field id="smtp_reply" label="Adresse de réponse" hint="Facultatif : où arrivent les réponses des clients.">
            <Input id="smtp_reply" type="email" value={form.reply_to} onChange={(e) => set({ reply_to: e.target.value })} />
          </Field>
          <Field id="smtp_bcc" label="Copie cachée systématique" hint="Facultatif : pour archiver chaque envoi.">
            <Input id="smtp_bcc" type="email" value={form.bcc} onChange={(e) => set({ bcc: e.target.value })} />
          </Field>
        </div>
        <ErrorAlert error={save.error} />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />} Enregistrer
          </Button>
          {save.isSuccess && (
            <span className="flex items-center gap-1 text-sm text-emerald-700">
              <Check className="size-4" /> Enregistré
            </span>
          )}
        </div>
      </form>
      <div className="h-fit space-y-3 rounded-xl border bg-card p-5 shadow-xs">
        <p className="font-medium">Tester l'envoi</p>
        <p className="text-sm text-muted-foreground">Enregistrez d'abord les réglages, puis envoyez-vous un mail d'essai.</p>
        <Field id="smtp_test" label="Destinataire">
          <Input id="smtp_test" type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
        </Field>
        <Button variant="outline" disabled={!initial.configured || !testTo.trim() || test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <LoaderCircle className="animate-spin" /> : <Send />} Envoyer un test
        </Button>
        <ErrorAlert error={test.error} />
        {test.isSuccess && <p className="text-sm text-emerald-700">Mail d'essai envoyé : vérifiez la boîte de réception.</p>}
      </div>
    </div>
  )
}

function TemplatesTab() {
  const { company } = useAuth()
  const templates = useQuery({ queryKey: ['mail-templates', company?.id], queryFn: () => api<MailTemplate[]>('/mail/templates') })
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Les champs entre accolades (<code>{'{numero}'}</code>, <code>{'{montant}'}</code>…) sont remplacés à l'envoi. Le message reste modifiable dans la fenêtre d'envoi.
      </p>
      <ErrorAlert error={templates.error} />
      {templates.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {templates.data?.map((t) => <TemplateCard key={`${company?.id}-${t.kind}-${t.subject}-${t.body.length}`} template={t} />)}
    </div>
  )
}

function TemplateCard({ template }: { template: MailTemplate }) {
  const queryClient = useQueryClient()
  const [subject, setSubject] = useState(template.subject)
  const [body, setBody] = useState(template.body)
  const dirty = subject !== template.subject || body !== template.body
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['mail-templates'] })
  const save = useMutation({
    mutationFn: () => api<MailTemplate>(`/mail/templates/${template.kind}`, { method: 'PUT', body: { subject, body } }),
    onSuccess: refresh,
  })
  const reset = useMutation({
    mutationFn: () => api<MailTemplate>(`/mail/templates/${template.kind}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  return (
    <div className="space-y-3 rounded-xl border bg-card p-5 shadow-xs">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium">{template.label}</p>
        <Badge variant={template.customized ? 'accent' : 'secondary'}>{template.customized ? 'Personnalisé' : 'Modèle par défaut'}</Badge>
      </div>
      <Field id={`tpl_subject_${template.kind}`} label="Objet">
        <Input id={`tpl_subject_${template.kind}`} value={subject} onChange={(e) => setSubject(e.target.value)} />
      </Field>
      <Field id={`tpl_body_${template.kind}`} label="Message">
        <Textarea id={`tpl_body_${template.kind}`} rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
      </Field>
      <p className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
        Champs :
        {template.fields.map((f) => (
          <code key={f} className="rounded bg-secondary px-1.5 py-0.5">{`{${f}}`}</code>
        ))}
      </p>
      <ErrorAlert error={save.error ?? reset.error} />
      <div className="flex gap-2">
        <Button size="sm" disabled={!dirty || !subject.trim() || !body.trim() || save.isPending} onClick={() => save.mutate()}>
          <Save /> Enregistrer
        </Button>
        {template.customized && (
          <Button size="sm" variant="outline" disabled={reset.isPending} onClick={() => reset.mutate()}>
            <RotateCcw /> Revenir au modèle par défaut
          </Button>
        )}
      </div>
    </div>
  )
}

const PAGE_SIZE = 25

function HistoryTab() {
  const { company } = useAuth()
  const queryClient = useQueryClient()
  const [params, update] = useUrlState()
  const page = Number(params.get('page') ?? 0)
  const status = params.get('statut') ?? ''
  const messages = useQuery({
    queryKey: ['mail-messages', company?.id, page, status],
    queryFn: () => {
      const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
      if (status) q.set('status', status)
      return api<{ items: MailMessage[]; total: number }>(`/mail/messages?${q}`)
    },
    refetchInterval: (query) => (query.state.data?.items.some((m) => m.status === 'en_attente') ? 3000 : false),
  })
  const retry = useMutation({
    mutationFn: (m: MailMessage) => api<MailMessage>(`/mail/messages/${m.id}/retry`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mail-messages'] }),
  })
  return (
    <div className="space-y-3">
      <NativeSelect className="w-48" aria-label="Statut" value={status} onChange={(e) => update({ statut: e.target.value || null, page: null })}>
        <option value="">Tous les envois</option>
        {Object.entries(MAIL_STATUSES).map(([k, v]) => (
          <option key={k} value={k}>
            {v.label}
          </option>
        ))}
      </NativeSelect>
      <ErrorAlert error={messages.error ?? retry.error} />
      {messages.isPending && <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
      {messages.data?.items.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">Aucun envoi.</p>}
      <div className="divide-y rounded-xl border bg-card shadow-xs">
        {messages.data?.items.map((m) => (
          <div key={m.id} className="flex flex-wrap items-start gap-3 p-4">
            <div className="min-w-0 flex-1 space-y-1">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                {m.subject}
                <Badge variant={MAIL_STATUSES[m.status].variant}>{MAIL_STATUSES[m.status].label}</Badge>
              </p>
              <p className="text-xs text-muted-foreground">
                {formatDateTime(m.sent_at ?? m.created_at)} · à {m.to_addrs.replaceAll(',', ', ')}
                {m.cc_addrs && ` · copie ${m.cc_addrs.replaceAll(',', ', ')}`}
                {m.attempts > 1 && ` · ${m.attempts} tentatives`}
              </p>
              {m.error && <p className="text-xs text-destructive">{m.error}</p>}
              <div className="flex flex-wrap gap-1.5">
                {m.attachments.map((a, i) => (
                  <button key={i} type="button" className="flex items-center gap-1 rounded border px-2 py-0.5 text-xs hover:bg-secondary" onClick={() => openFile(`/mail/messages/${m.id}/attachments/${i}`)}>
                    <FileText className="size-3" /> {a.filename}
                  </button>
                ))}
              </div>
            </div>
            {m.status === 'echec' && (
              <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate(m)}>
                <RotateCw /> Renvoyer
              </Button>
            )}
          </div>
        ))}
      </div>
      {messages.data && <Pagination page={page} pageSize={PAGE_SIZE} total={messages.data.total} noun={['envoi', 'envois']} onPage={(p) => update({ page: p ? String(p) : null })} />}
    </div>
  )
}

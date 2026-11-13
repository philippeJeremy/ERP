/** Types de la messagerie (miroir de l'API /mail). */

export interface MailMessage {
  id: number
  kind: string
  document_type: string | null
  document_id: number | null
  document_number: string | null
  to_addrs: string
  cc_addrs: string | null
  subject: string
  body: string
  status: 'en_attente' | 'envoye' | 'echec'
  error: string | null
  attempts: number
  created_at: string
  sent_at: string | null
  attachments: { filename: string; size: number }[]
}

export interface EmailDraft {
  to: string[]
  cc: string[]
  subject: string
  body: string
  attachments: string[]
  suggestions: { label: string; email: string }[]
  smtp_ready: boolean
  history: MailMessage[]
}

export interface SmtpSettings {
  configured: boolean
  enabled: boolean
  host: string | null
  port: number
  security: 'starttls' | 'ssl' | 'none'
  username: string | null
  has_password: boolean
  from_email: string | null
  from_name: string | null
  reply_to: string | null
  bcc: string | null
}

export interface MailTemplate {
  kind: string
  label: string
  subject: string
  body: string
  customized: boolean
  fields: string[]
}

export const MAIL_STATUSES = {
  en_attente: { label: 'En cours d’envoi', variant: 'secondary' },
  envoye: { label: 'Envoyé', variant: 'success' },
  echec: { label: 'Échec', variant: 'destructive' },
} as const

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
/** « a@b.fr, c@d.fr » → liste ; null si une adresse est invalide. */
export function parseEmails(value: string): string[] | null {
  const list = value
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean)
  return list.every((x) => EMAIL_RE.test(x)) ? list : null
}

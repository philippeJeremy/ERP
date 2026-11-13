/** Types et libellés du module tiers (miroir des schémas de l'API). */

export interface PartnerAddress {
  id: number
  kind: AddressKind
  label: string | null
  line1: string
  line2: string | null
  postal_code: string
  city: string
  country_code: string
  gln: string | null
  is_primary: boolean
}

export interface PartnerContact {
  id: number
  first_name: string | null
  last_name: string
  job_title: string | null
  email: string | null
  phone: string | null
  mobile: string | null
  notes: string | null
  is_primary: boolean
}

export interface Partner {
  id: number
  code: string
  name: string
  legal_form: string | null
  siret: string | null
  vat_number: string | null
  gln: string | null
  is_supplier: boolean
  is_customer: boolean
  parent: { id: number; code: string; name: string } | null
  email: string | null
  invoice_email: string | null
  phone: string | null
  website: string | null
  notes: string | null
  is_active: boolean
  supplier_account: string | null
  payment_method: PaymentMethod | null
  payment_days: number | null
  payment_end_of_month: boolean
  currency: string
  lead_time_days: number | null
  min_order_amount: string | null // montants : chaînes, jamais de float (« 1500.00 »)
  free_shipping_amount: string | null
  bank_name: string | null
  iban: string | null
  bic: string | null
  customer_kind: CustomerKind | null
  first_name: string | null
  vehicle_registration: string | null
  customer_account: string | null
  customer_payment_method: PaymentMethod | null
  customer_payment_days: number | null
  customer_payment_end_of_month: boolean
  credit_limit: string | null
  discount_pct: string
  discount_tire_pct: string | null
  discount_part_pct: string | null
  discount_accessory_pct: string | null
  addresses: PartnerAddress[]
  contacts: PartnerContact[]
  version: number
  created_at: string
  updated_at: string
}

export interface PartnerListItem {
  id: number
  code: string
  name: string
  siret: string | null
  city: string | null
  email: string | null
  phone: string | null
  contact_name: string | null
  is_supplier: boolean
  is_customer: boolean
  is_active: boolean
}

export interface PartnerPage {
  items: PartnerListItem[]
  total: number
}

export const PAYMENT_METHODS = {
  virement: 'Virement',
  prelevement: 'Prélèvement',
  cheque: 'Chèque',
  lcr: 'LCR (lettre de change)',
  carte: 'Carte bancaire',
  especes: 'Espèces',
} as const
export type PaymentMethod = keyof typeof PAYMENT_METHODS

export const CUSTOMER_KINDS = { pro: 'Professionnel', particulier: 'Particulier' } as const
export type CustomerKind = keyof typeof CUSTOMER_KINDS

export const ADDRESS_KINDS = {
  siege: { label: 'Siège social', hint: 'Adresse légale' },
  commande: { label: 'Commandes', hint: 'Où envoyer les bons de commande' },
  enlevement: { label: 'Enlèvement', hint: 'Où récupérer la marchandise' },
  retour: { label: 'Retours', hint: 'Où renvoyer les produits (garantie, erreur)' },
  facturation: { label: 'Facturation', hint: 'Qui émet les factures' },
  livraison: { label: 'Livraison', hint: 'Pour les clients' },
  autre: { label: 'Autre', hint: '' },
} as const
export type AddressKind = keyof typeof ADDRESS_KINDS

/** « 552 100 554 00017 » → « 55210055400017 » (comme l'API). */
export const compact = (v: string) => v.replace(/[\s.]/g, '').toUpperCase()

/** Clé de contrôle IBAN (modulo 97) : la même vérification que l'API, avant l'envoi. */
export function ibanIsValid(raw: string): boolean {
  const iban = compact(raw)
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(iban)) return false
  const digits = (iban.slice(4) + iban.slice(0, 4)).replace(/[A-Z]/g, (c) => String(c.charCodeAt(0) - 55))
  // Calcul par morceaux : le nombre est trop grand pour un Number JavaScript.
  let rest = 0
  for (const d of digits) rest = (rest * 10 + Number(d)) % 97
  return rest === 1
}

/** « IBAN groupé par 4 » pour l'affichage : FR76 3000 6000 … */
export const formatIban = (iban: string) => iban.replace(/(.{4})/g, '$1 ').trim()

function terms(days: number | null, endOfMonth: boolean, method: PaymentMethod | null): string | null {
  const parts: string[] = []
  if (days !== null) parts.push(days === 0 ? 'Comptant' : `${days} jours${endOfMonth ? ' fin de mois' : ''}`)
  if (method) parts.push(`par ${PAYMENT_METHODS[method].toLowerCase()}`)
  return parts.length ? parts.join(', ') : null
}

/** « 45 jours fin de mois, par virement » (conditions d'achat) */
export const describePaymentTerms = (p: Partner) => terms(p.payment_days, p.payment_end_of_month, p.payment_method)

/** Conditions de règlement du client. */
export const describeCustomerTerms = (p: Partner) => terms(p.customer_payment_days, p.customer_payment_end_of_month, p.customer_payment_method)

/** Nom affiché : « DUPONT Jean » pour un particulier. */
export const partnerDisplayName = (p: Pick<Partner, 'name' | 'first_name'>) => (p.first_name ? `${p.name} ${p.first_name}` : p.name)

const money = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
export function formatMoney(amount: string | null, currency = 'EUR'): string {
  if (amount === null) return '—'
  return currency === 'EUR'
    ? money.format(Number(amount))
    : new Intl.NumberFormat('fr-FR', { style: 'currency', currency }).format(Number(amount))
}

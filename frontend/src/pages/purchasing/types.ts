/** Types et libellés des achats (miroir des schémas de l'API). */

export interface Site {
  id: number
  code: string
  name: string
  address_line1: string
  address_line2: string | null
  postal_code: string
  city: string
  country_code: string
  phone: string | null
  delivery_notes: string | null
  gln: string | null
  is_default: boolean
  is_active: boolean
  version: number
}

export type OrderStatus = 'brouillon' | 'a_valider' | 'validee' | 'envoyee' | 'confirmee' | 'partielle' | 'recue' | 'cloturee' | 'annulee'

export const ORDER_STATUSES: Record<OrderStatus, { label: string; variant: 'secondary' | 'accent' | 'success' | 'outline' | 'destructive' }> = {
  brouillon: { label: 'Brouillon', variant: 'outline' },
  a_valider: { label: 'À valider', variant: 'accent' },
  validee: { label: 'Validée', variant: 'secondary' },
  envoyee: { label: 'Envoyée', variant: 'secondary' },
  confirmee: { label: 'Confirmée', variant: 'secondary' },
  partielle: { label: 'Reçue en partie', variant: 'accent' },
  recue: { label: 'Reçue', variant: 'success' },
  cloturee: { label: 'Clôturée', variant: 'outline' },
  annulee: { label: 'Annulée', variant: 'destructive' },
}

export interface OrderLine {
  id: number
  line_no: number
  article_id: number | null
  supplier_ref: string | null
  designation: string
  quantity: string
  unit_price: string
  discount_pct: string
  line_total: string
  confirmed_qty: string | null
  confirmed_date: string | null
  received_qty: string
}

export interface Reception {
  id: number
  number: string
  received_on: string
  delivery_note: string | null
  note: string | null
  created_at: string
  lines: { order_line_id: number; quantity: string; location_id: number | null; dot: string }[]
}

export interface Order {
  id: number
  number: string | null
  status: OrderStatus
  supplier: {
    id: number
    code: string
    name: string
    payment_terms: string | null
    min_order_amount: string | null
    free_shipping_amount: string | null
    lead_time_days: number | null
    email: string | null
    phone: string | null
    order_address: string[]
  }
  site: { id: number; code: string; name: string; city: string }
  order_date: string | null
  expected_date: string | null
  currency: string
  supplier_reference: string | null
  supplier_note: string | null
  internal_note: string | null
  total_ht: string
  submitted_at: string | null
  approved_at: string | null
  rejection_reason: string | null
  sent_at: string | null
  confirmed_at: string | null
  closed_at: string | null
  cancel_reason: string | null
  approval_threshold: string | null
  lines: OrderLine[]
  receptions: Reception[]
  warnings: string[]
  version: number
  created_at: string
  updated_at: string
}

export interface OrderListItem {
  id: number
  number: string | null
  status: OrderStatus
  partner_id: number
  partner_name: string
  site_name: string
  order_date: string | null
  expected_date: string | null
  total_ht: string
  line_count: number
  received_ratio: number
}

export const orderTitle = (o: { number: string | null; id: number }) => o.number ?? `Brouillon n° ${o.id}`

/** « 2 » ou « 2,5 » (quantités à 3 décimales). */
export const qty = (v: string | number) => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 3 })

export const formatDate = (iso: string | null) => (iso ? new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('fr-FR') : '—')

const eur = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
export const money = (v: string | number | null) => (v === null ? '—' : eur.format(Number(v)))

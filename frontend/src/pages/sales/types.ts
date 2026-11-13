/** Types et libellés des ventes (miroir des schémas de l'API /sales). */
import type { ArticleBrief } from '@/pages/inventory/types'

export type QuoteStatus = 'brouillon' | 'envoye' | 'accepte' | 'refuse' | 'annule'
export type OrderStatus = 'brouillon' | 'confirmee' | 'partielle' | 'livree' | 'cloturee' | 'annulee'
type Variant = 'secondary' | 'accent' | 'success' | 'outline' | 'destructive'

export const QUOTE_STATUSES: Record<QuoteStatus, { label: string; variant: Variant }> = {
  brouillon: { label: 'Brouillon', variant: 'secondary' },
  envoye: { label: 'Envoyé', variant: 'accent' },
  accepte: { label: 'Accepté', variant: 'success' },
  refuse: { label: 'Refusé', variant: 'destructive' },
  annule: { label: 'Annulé', variant: 'outline' },
}

export const ORDER_STATUSES: Record<OrderStatus, { label: string; variant: Variant }> = {
  brouillon: { label: 'Brouillon', variant: 'secondary' },
  confirmee: { label: 'Confirmée', variant: 'accent' },
  partielle: { label: 'Partiellement livrée', variant: 'accent' },
  livree: { label: 'Livrée', variant: 'success' },
  cloturee: { label: 'Clôturée', variant: 'outline' },
  annulee: { label: 'Annulée', variant: 'outline' },
}

export interface SalesLine {
  id: number
  line_no: number
  article: ArticleBrief | null
  designation: string
  quantity: string
  unit_price: string
  discount_pct: string
  eco_fee: string
  vat_rate: string
  line_total: string
  eco_total: string
  unit_cost: string | null
  margin: string | null
}

export interface OrderLine extends SalesLine {
  dot: string
  delivered_qty: string
  remaining_qty: string
  on_hand: string | null
}

export interface CustomerInfo {
  id: number
  code: string
  name: string
  kind: 'pro' | 'particulier'
  payment_terms: string | null
  email: string | null
  phone: string | null
  vehicle_registration: string | null
  billing_address: string[]
  delivery_address: string[]
}

interface DocBase {
  id: number
  number: string
  customer: CustomerInfo
  site: { id: number; code: string; name: string }
  customer_reference: string | null
  customer_note: string | null
  internal_note: string | null
  total_ht: string
  total_eco: string
  total_vat: string
  total_ttc: string
  vat: { rate: string; base: string; vat: string }[]
  margin: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface Quote extends DocBase {
  status: QuoteStatus
  quote_date: string
  valid_until: string
  expired: boolean
  sent_at: string | null
  decided_at: string | null
  refusal_reason: string | null
  order: { id: number; number: string } | null
  lines: SalesLine[]
}

export interface Delivery {
  id: number
  number: string
  delivered_on: string
  carrier: string | null
  note: string | null
  lines: { order_line_id: number; line_no: number; designation: string; quantity: string; location_code: string | null; dot: string }[]
  created_at: string
}

export interface Order extends DocBase {
  status: OrderStatus
  order_date: string
  requested_date: string | null
  delivery_address: string | null
  confirmed_at: string | null
  closed_at: string | null
  cancel_reason: string | null
  quote: { id: number; number: string } | null
  credit: { limit: string | null; outstanding: string }
  lines: OrderLine[]
  deliveries: Delivery[]
}

export interface QuoteListItem {
  id: number
  number: string
  status: QuoteStatus
  expired: boolean
  customer_id: number
  customer_name: string
  quote_date: string
  valid_until: string
  total_ht: string
  total_ttc: string
}

export interface OrderListItem {
  id: number
  number: string
  status: OrderStatus
  customer_id: number
  customer_name: string
  site_name: string
  order_date: string
  requested_date: string | null
  total_ht: string
  total_ttc: string
}

export interface Pricing {
  article: ArticleBrief
  unit_price: string | null
  discount_pct: string
  eco_fee: string
  vat_rate: string
  net_price: string | null
  on_hand: string
  available: string
  average_cost: string
}

export interface PriceRow {
  article: ArticleBrief
  kind: 'pneu' | 'piece' | 'accessoire'
  sale_price: string | null
  eco_fee: string
  average_cost: string
  margin_pct: string | null
  updated_at: string | null
}

export interface CustomerActivity {
  credit: { limit: string | null; outstanding: string }
  quotes: QuoteListItem[]
  orders: OrderListItem[]
}

const pct = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 })
export const fmtPct = (v: string | number) => `${pct.format(Number(v))} %`
export const today = () => new Date().toISOString().slice(0, 10)
const dateFormat = new Intl.DateTimeFormat('fr-FR')
export const fmtDate = (v: string | null) => (v ? dateFormat.format(new Date(v + 'T00:00:00')) : '—')

/** Types et libellés de la facturation (miroir des schémas de l'API /billing). */

export type PaymentStatus = 'brouillon' | 'a_payer' | 'partielle' | 'payee' | 'en_retard'
type Variant = 'secondary' | 'accent' | 'success' | 'outline' | 'destructive'

export const PAYMENT_STATUSES: Record<PaymentStatus, { label: string; variant: Variant }> = {
  brouillon: { label: 'Brouillon', variant: 'secondary' },
  a_payer: { label: 'À payer', variant: 'accent' },
  partielle: { label: 'Partiellement payée', variant: 'accent' },
  payee: { label: 'Payée', variant: 'success' },
  en_retard: { label: 'En retard', variant: 'destructive' },
}

/** Pour un avoir, « payé » veut dire « crédit entièrement utilisé ». */
export function statusOf(kind: string, status: PaymentStatus) {
  if (kind === 'avoir' && status === 'payee') return { label: 'Soldé', variant: 'success' as Variant }
  if (kind === 'avoir' && (status === 'a_payer' || status === 'partielle')) return { label: 'Crédit disponible', variant: 'accent' as Variant }
  return PAYMENT_STATUSES[status]
}

export const PAYMENT_METHODS = {
  virement: 'Virement',
  cheque: 'Chèque',
  carte: 'Carte bancaire',
  especes: 'Espèces',
  prelevement: 'Prélèvement',
  lcr: 'LCR',
} as const
export type PaymentMethod = keyof typeof PAYMENT_METHODS

export interface InvoiceLine {
  id: number
  line_no: number
  delivery_id: number | null
  delivery_number: string | null
  original_line_id: number | null
  article_id: number | null
  article_code: string | null
  designation: string
  quantity: string
  unit_price: string
  discount_pct: string
  eco_fee: string
  vat_rate: string
  line_total: string
  eco_total: string
  creditable_qty: string | null
}

export interface Allocation {
  id: number
  amount: string
  allocated_on: string
  source: 'reglement' | 'avoir'
  source_id: number
  source_number: string
  invoice_id: number
  invoice_number: string | null
}

export interface Invoice {
  id: number
  number: string | null
  kind: 'facture' | 'avoir'
  status: 'brouillon' | 'emise'
  customer_id: number
  customer_code: string
  customer_name: string
  customer_address: string | null
  customer_vat: string | null
  customer_siren: string | null
  customer_kind: string
  issue_date: string | null
  due_date: string | null
  delivery_date: string | null
  payment_terms: string | null
  customer_reference: string | null
  note: string | null
  total_ht: string
  total_eco: string
  total_vat: string
  total_ttc: string
  vat: { rate: string; base: string; vat: string }[]
  paid_amount: string
  balance: string
  payment_status: PaymentStatus
  days_late: number
  original: { id: number; number: string | null } | null
  credit_notes: { id: number; number: string | null }[]
  deliveries: { id: number; number: string | null }[]
  allocations: Allocation[]
  reminder_count: number
  last_reminder_at: string | null
  issued_at: string | null
  lines: InvoiceLine[]
  version: number
  created_at: string
}

export interface InvoiceListItem {
  id: number
  number: string | null
  kind: 'facture' | 'avoir'
  status: 'brouillon' | 'emise'
  customer_id: number
  customer_name: string
  issue_date: string | null
  due_date: string | null
  total_ht: string
  total_ttc: string
  balance: string
  payment_status: PaymentStatus
  days_late: number
}

export interface CustomerToBill {
  customer_id: number
  customer_code: string
  customer_name: string
  total_ht: string
  deliveries: { id: number; number: string; delivered_on: string; order_id: number; order_number: string; customer_reference: string | null; total_ht: string }[]
}

export interface Payment {
  id: number
  number: string
  customer_id: number
  customer_name: string
  paid_on: string
  amount: string
  method: PaymentMethod
  reference: string | null
  note: string | null
  allocated: string
  unallocated: string
  allocations: Allocation[]
  created_at: string
}

export interface CustomerAccount {
  customer_id: number
  customer_name: string
  invoices: InvoiceListItem[]
  credit_notes: InvoiceListItem[]
  unallocated_payments: Payment[]
  total_due: string
  overdue: string
  available_credit: string
  uninvoiced: string
}

export interface AgingRow {
  customer_id: number
  customer_name: string
  not_due: string
  late_30: string
  late_60: string
  late_more: string
  total: string
  last_reminder_at: string | null
}

export interface SupplierLine {
  id: number
  line_no: number
  reception_line_id: number | null
  reception_number: string | null
  order_number: string | null
  article_id: number | null
  designation: string
  quantity: string
  unit_price: string
  expected_quantity: string | null
  expected_price: string | null
  vat_rate: string
  line_total: string
  qty_gap: string | null
  price_gap: string | null
}

export interface SupplierInvoice {
  id: number
  number: string
  status: 'brouillon' | 'bon_a_payer' | 'annulee'
  partner_id: number
  partner_name: string
  supplier_number: string
  invoice_date: string
  due_date: string | null
  total_ht: string
  total_vat: string
  total_ttc: string
  computed_ht: string
  computed_vat: string
  gaps: string[]
  paid_amount: string
  balance: string
  note: string | null
  approved_at: string | null
  approval_note: string | null
  lines: SupplierLine[]
  payments: { id: number; paid_on: string; amount: string; method: string; reference: string | null }[]
  version: number
  created_at: string
}

export interface SupplierInvoiceListItem {
  id: number
  number: string
  status: SupplierInvoice['status']
  partner_id: number
  partner_name: string
  supplier_number: string
  invoice_date: string
  due_date: string | null
  total_ttc: string
  balance: string
  has_gaps: boolean
}

export const SUPPLIER_STATUSES: Record<SupplierInvoice['status'], { label: string; variant: Variant }> = {
  brouillon: { label: 'À contrôler', variant: 'secondary' },
  bon_a_payer: { label: 'Bon à payer', variant: 'accent' },
  annulee: { label: 'Annulée', variant: 'outline' },
}

export interface Entry {
  journal: string
  date: string
  piece: string
  account: string
  aux_account: string | null
  aux_label: string | null
  label: string
  debit: string
  credit: string
}

export interface BillingSettings {
  default_payment_days: number
  default_vat_rate: string
  customer_account: string
  supplier_account: string
  sales_goods_account: string
  sales_services_account: string
  eco_fee_account: string
  vat_collected_account: string
  purchases_account: string
  vat_deductible_account: string
  bank_account: string
  cash_account: string
  sales_journal: string
  purchases_journal: string
  bank_journal: string
}

const MONEY_RE = /^\d{1,12}([.,]\d{1,2})?$/
export const moneyOk = (v: string) => MONEY_RE.test(v.trim()) && Number(v.replace(',', '.')) > 0
export const toDec = (v: string) => v.trim().replace(',', '.')

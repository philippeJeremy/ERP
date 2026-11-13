/** Types et libellés du stock (miroir des schémas de l'API /inventory). */

export interface ArticleBrief {
  id: number
  code: string
  designation: string
  ean: string | null
  brand: string | null
  size: string | null
}

export interface SiteBrief {
  id: number
  code: string
  name: string
}

export interface LocationBrief {
  id: number
  code: string
}

export interface Location {
  id: number
  site_id: number
  code: string
  name: string | null
  is_default: boolean
  is_active: boolean
  version: number
}

export interface StockRow {
  article: ArticleBrief
  quantity: string
  reserved: string
  available: string
  average_cost: string
  value: string
  oldest_dot: string | null
}

export interface StockPage {
  items: StockRow[]
  total: number
  total_quantity: string
  total_value: string
}

export type MoveKind = 'reception' | 'transfert' | 'inventaire' | 'ajustement' | 'livraison'

export interface Move {
  id: number
  moved_at: string
  kind: MoveKind
  article: ArticleBrief
  site: SiteBrief
  location: LocationBrief
  dot: string
  quantity: string
  unit_cost: string
  source: string | null
  reference: string | null
  reason: string | null
  note: string | null
  created_by: number | null
}

export interface ArticleStock {
  article: ArticleBrief
  quantity: string
  average_cost: string
  value: string
  reserved: string
  sites: { site: SiteBrief; quantity: string; reserved: string; available: string }[]
  levels: { site: SiteBrief; location: LocationBrief; dot: string; quantity: string }[]
  moves: Move[]
}

export interface TransferListItem {
  id: number
  number: string
  from_site: SiteBrief
  to_site: SiteBrief
  transferred_on: string
  note: string | null
  line_count: number
  total_quantity: string
  created_at: string
}

export interface Transfer extends TransferListItem {
  moves: Move[]
}

export type CountStatus = 'en_cours' | 'valide' | 'annule'

export interface CountListItem {
  id: number
  number: string
  site: SiteBrief
  location: LocationBrief | null
  status: CountStatus
  note: string | null
  line_count: number
  counted_count: number
  created_at: string
  validated_at: string | null
}

export interface CountLine {
  id: number
  article: ArticleBrief
  location: LocationBrief
  dot: string
  expected_qty: string
  counted_qty: string | null
  difference: string | null
}

export interface Count extends CountListItem {
  version: number
  lines: CountLine[]
  value_difference: string
}

export const MOVE_KINDS: Record<MoveKind, string> = {
  reception: 'Réception',
  transfert: 'Transfert',
  inventaire: 'Inventaire',
  ajustement: 'Ajustement',
  livraison: 'Livraison',
}

export const ADJUST_REASONS = {
  casse: 'Casse',
  perte: 'Perte',
  vol: 'Vol',
  erreur: 'Erreur de saisie',
  retour: 'Retour client',
  echantillon: 'Échantillon / prêt',
  autre: 'Autre',
} as const

export const COUNT_STATUSES: Record<CountStatus, { label: string; variant: 'accent' | 'success' | 'outline' }> = {
  en_cours: { label: 'En cours', variant: 'accent' },
  valide: { label: 'Validé', variant: 'success' },
  annule: { label: 'Annulé', variant: 'outline' },
}

/** DOT : semaine 01-53 puis année (« 2324 » = semaine 23 de 2024). Vide autorisé. */
export const DOT_RE = /^$|^(0[1-9]|[1-4]\d|5[0-3])\d{2}$/

/** « 2324 » → « S23/2024 ». */
export function dotLabel(dot: string | null | undefined): string {
  if (!dot) return '—'
  return `S${dot.slice(0, 2)}/20${dot.slice(2)}`
}

/** Âge d'un pneu en années, d'après son DOT (un pneu se vend « neuf » jusqu'à ~3-5 ans). */
export function dotAgeYears(dot: string, now = new Date()): number {
  const year = 2000 + Number(dot.slice(2))
  const week = Number(dot.slice(0, 2))
  const made = new Date(year, 0, 1 + (week - 1) * 7)
  return (now.getTime() - made.getTime()) / (365.25 * 86400000)
}

const qtyFormat = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 3 })
const moneyFormat = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
const costFormat = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 4 })

export const fmtQty = (v: string | number) => qtyFormat.format(Number(v))
export const fmtMoney = (v: string | number) => moneyFormat.format(Number(v))
export const fmtCost = (v: string | number) => costFormat.format(Number(v))


export interface OriginOption {
  /** « id-emplacement|DOT » ; DOT « * » = les plus anciens d'abord (FIFO). */
  value: string
  label: string
  max: number
}

/** Les lots d'un article dans un dépôt, proposés comme origine d'un transfert. */
export function originOptions(stock: ArticleStock | undefined, siteId: number): OriginOption[] {
  const levels = stock?.levels.filter((l) => l.site.id === siteId) ?? []
  const byLocation = new Map<number, { code: string; total: number; count: number }>()
  for (const l of levels) {
    const e = byLocation.get(l.location.id) ?? { code: l.location.code, total: 0, count: 0 }
    byLocation.set(l.location.id, { code: e.code, total: e.total + Number(l.quantity), count: e.count + 1 })
  }
  return [
    ...[...byLocation.entries()]
      .filter(([, e]) => e.count > 1)
      .map(([id, e]) => ({ value: `${id}|*`, label: `${e.code} · les plus anciens d'abord (${fmtQty(e.total)})`, max: e.total })),
    ...levels.map((l) => ({
      value: `${l.location.id}|${l.dot}`,
      label: `${l.location.code} · ${l.dot ? `DOT ${l.dot} (${dotLabel(l.dot)})` : 'sans DOT'} — ${fmtQty(l.quantity)}`,
      max: Number(l.quantity),
    })),
  ]
}

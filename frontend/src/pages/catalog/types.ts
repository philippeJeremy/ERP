/** Types et libellés du catalogue (miroir des schémas de l'API). */

export const KINDS = { pneu: 'Pneu', piece: 'Pièce', accessoire: 'Accessoire' } as const
export type Kind = keyof typeof KINDS

export const VEHICLE_TYPES = {
  tourisme: 'Tourisme',
  '4x4': '4x4 / SUV',
  utilitaire: 'Utilitaire',
  moto: 'Moto / scooter',
  poids_lourd: 'Poids lourd',
  agricole: 'Agricole',
  genie_civil: 'Génie civil',
  autre: 'Autre',
} as const
export type VehicleType = keyof typeof VEHICLE_TYPES

export const SEASONS = { ete: 'Été', hiver: 'Hiver', '4_saisons': '4 saisons' } as const
export type Season = keyof typeof SEASONS

export interface TireSpec {
  vehicle_type: VehicleType
  season: Season | null
  width: string | null
  aspect_ratio: number | null
  construction: string | null
  rim: string | null
  load_index: string | null
  speed_index: string | null
  size_code: string | null
  size: string | null
  reinforced: boolean
  runflat: boolean
  studded: boolean
  three_pmsf: boolean
  mud_snow: boolean
  fuel_class: string | null
  wet_class: string | null
  noise_db: number | null
  noise_class: string | null
  eprel_id: string | null
}

export interface Article {
  id: number
  code: string
  kind: Kind
  ean: string | null
  brand: { id: number; name: string } | null
  manufacturer_ref: string | null
  designation: string
  category: string | null
  unit: string
  notes: string | null
  is_active: boolean
  tire: TireSpec | null
  version: number
  created_at: string
  updated_at: string
}

export interface ArticleListItem {
  id: number
  code: string
  kind: Kind
  ean: string | null
  brand: string | null
  designation: string
  size: string | null
  season: Season | null
  vehicle_type: VehicleType | null
  fuel_class: string | null
  wet_class: string | null
  noise_db: number | null
  is_active: boolean
  supplier_count: number
  best_price: string | null
}

export interface ArticleSupplier {
  id: number
  article: { id: number; code: string; designation: string; ean: string | null; brand: string | null; size: string | null }
  partner: { id: number; code: string; name: string }
  supplier_ref: string | null
  purchase_price: string | null
  currency: string
  is_preferred: boolean
  is_discontinued: boolean
  discontinued_at: string | null
  price_updated_at: string | null
  version: number
}

export interface Page<T> {
  items: T[]
  total: number
}

// --- Imports ---------------------------------------------------------------------

export interface ImportProfile {
  id: number
  partner_id: number
  name: string
  file_format: 'csv' | 'excel'
  delimiter: string | null
  encoding: string | null
  sheet_name: string | null
  header_row: number
  mapping: Record<string, string>
  full_catalog: boolean
  default_kind: Kind
  default_vehicle_type: VehicleType | null
  parse_designation: boolean
  version: number
  updated_at: string
}

export interface FilePreview {
  file_format: 'csv' | 'excel'
  delimiter: string | null
  encoding: string | null
  sheets: string[] | null
  sheet_name: string | null
  headers: string[]
  rows: string[][]
  suggested_mapping: Record<string, string>
  fields: Record<string, string>
}

export type RunStatus = 'analyse' | 'pret' | 'application' | 'termine' | 'erreur' | 'annule'
export type LineStatus = 'nouveau' | 'maj' | 'inchange' | 'reactive' | 'arret' | 'erreur'

export interface ImportRun {
  id: number
  partner_id: number
  partner_name: string | null
  profile_id: number | null
  source: string
  filename: string
  file_size: number
  status: RunStatus
  full_catalog: boolean
  total_lines: number
  new_count: number
  updated_count: number
  unchanged_count: number
  reactivated_count: number
  discontinued_count: number
  error_count: number
  active_before: number
  message: string | null
  needs_confirmation: boolean
  created_at: string
  analyzed_at: string | null
  applied_at: string | null
}

export interface ImportLine {
  id: number
  line_no: number | null
  status: LineStatus
  article_id: number | null
  data: Record<string, unknown> & { tire?: Record<string, unknown> }
  old_price: string | null
  new_price: string | null
  error: string | null
}

export const RUN_STATUSES: Record<RunStatus, { label: string; variant: 'secondary' | 'accent' | 'success' | 'outline' | 'destructive' }> = {
  analyse: { label: 'Analyse en cours', variant: 'secondary' },
  pret: { label: 'À valider', variant: 'accent' },
  application: { label: 'Application en cours', variant: 'secondary' },
  termine: { label: 'Appliqué', variant: 'success' },
  erreur: { label: 'Erreur', variant: 'destructive' },
  annule: { label: 'Annulé', variant: 'outline' },
}

// --- Formats -----------------------------------------------------------------------

const price2 = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 4 })

/** Prix d'achat : 2 décimales au moins, jusqu'à 4 (0,0350 €). */
export function formatPrice(value: string | null | undefined): string {
  return value === null || value === undefined ? '—' : price2.format(Number(value))
}

/** Écart de prix en % : « +2,4 % ». */
export function priceChange(oldPrice: string | null, newPrice: string | null): string | null {
  if (!oldPrice || !newPrice || Number(oldPrice) === 0) return null
  const pct = ((Number(newPrice) - Number(oldPrice)) / Number(oldPrice)) * 100
  return `${pct > 0 ? '+' : ''}${pct.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`
}

export const formatSize = (bytes: number) =>
  bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mo` : `${Math.ceil(bytes / 1024)} Ko`

/** Même contrôle que l'API : clé des codes-barres EAN/GTIN (modulo 10). */
export function gtinIsValid(code: string): boolean {
  if (!/^(\d{8}|\d{12,14})$/.test(code)) return false
  const digits = code.split('').map(Number)
  const check = digits.pop()!
  const total = digits.reverse().reduce((sum, d, i) => sum + d * (i % 2 === 0 ? 3 : 1), 0)
  return (10 - (total % 10)) % 10 === check
}


// --- Relèves automatiques ----------------------------------------------------------

export type Protocol = 'sftp' | 'ftps' | 'ftp'

export interface ImportSource {
  id: number
  partner_id: number
  partner_name: string | null
  profile_id: number | null
  profile_name: string | null
  name: string
  protocol: Protocol
  host: string
  port: number
  username: string
  auth_method: 'password' | 'key'
  has_secret: boolean
  host_key: string | null
  tls_verify: boolean
  remote_dir: string
  pattern: string
  interval_hours: number
  auto_apply: boolean
  is_active: boolean
  next_check_at: string | null
  last_check_at: string | null
  last_status: 'ok' | 'aucun_fichier' | 'erreur' | null
  last_message: string | null
  last_run_id: number | null
  version: number
}

export interface ConnectionTest {
  host_key: string | null
  host_key_changed: boolean
  files: { name: string; size: number; mtime: string | null; already_seen: boolean }[]
}

export const PROTOCOLS: Record<Protocol, { label: string; port: number; hint: string }> = {
  sftp: { label: 'SFTP', port: 22, hint: 'Par SSH, chiffré. Le plus sûr : à privilégier.' },
  ftps: { label: 'FTPS', port: 21, hint: 'FTP protégé par TLS, chiffré.' },
  ftp: { label: 'FTP', port: 21, hint: 'Non chiffré : mot de passe et fichier circulent en clair. À éviter.' },
}

export const INTERVALS: Record<number, string> = {
  1: 'Toutes les heures',
  2: 'Toutes les 2 heures',
  4: 'Toutes les 4 heures',
  6: 'Toutes les 6 heures',
  12: 'Deux fois par jour',
  24: 'Une fois par jour',
  48: 'Tous les 2 jours',
  168: 'Une fois par semaine',
}

/**
 * Client HTTP de l'API.
 *
 * Sécurité des jetons :
 *  - le jeton d'ACCÈS (15 min) vit uniquement en mémoire (variable JavaScript) :
 *    pas de localStorage, où un script malveillant (XSS) pourrait le lire ;
 *  - le REFRESH token (7 jours) est dans un cookie httpOnly posé par l'API :
 *    JavaScript ne peut ni le lire ni le voler. Le navigateur l'envoie tout seul,
 *    uniquement à /api/auth/*.
 * Recharger la page efface le jeton d'accès : on en redemande un avec le cookie
 * (`refreshAccessToken`), l'utilisateur reste connecté.
 */

const API_BASE = '/api'
const COMPANY_KEY = 'erp.companyId'

let accessToken: string | null = null
let lastTokenAt = 0 // horodatage du dernier jeton obtenu (connexion ou renouvellement)
let onSessionExpired: (() => void) | null = null

/** Quand le dernier jeton a été obtenu : sert à renouveler la session d'un utilisateur actif. */
export function getLastTokenAt(): number {
  return lastTokenAt
}

/** Appelé quand la session est définitivement perdue (le frontend repasse sur la page de connexion). */
export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler
}

// --- Société courante --------------------------------------------------------------
// Pas sensible (c'est un simple id, l'API vérifie les droits) : localStorage convient,
// et la société choisie est retrouvée au prochain chargement.

export function getCompanyId(): number | null {
  const v = localStorage.getItem(COMPANY_KEY)
  return v ? Number(v) : null
}

export function setCompanyId(id: number | null) {
  if (id === null) localStorage.removeItem(COMPANY_KEY)
  else localStorage.setItem(COMPANY_KEY, String(id))
}

// --- Erreurs -----------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    /* réponse sans JSON */
  }
  // Format des erreurs métier de l'API : {"error": {"code", "message"}}
  const err = (body as { error?: { code: string; message: string } } | null)?.error
  if (err) return new ApiError(response.status, err.code, err.message)
  // Erreur de validation FastAPI (422) : {"detail": [...]}
  if (response.status === 422) return new ApiError(422, 'validation', 'Données invalides')
  return new ApiError(response.status, 'http_error', `Erreur ${response.status}`)
}

// --- Jetons ------------------------------------------------------------------------

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
let refreshing: Promise<boolean> | null = null

/**
 * Demande un nouveau jeton d'accès avec le cookie de session.
 * « Single flight » : si 5 requêtes reçoivent un 401 en même temps, un seul appel
 * à /auth/refresh est fait, les 5 attendent son résultat.
 */
export function refreshAccessToken(): Promise<boolean> {
  refreshing ??= (async () => {
    // Si l'utilisateur se connecte PENDANT ce renouvellement (page de connexion ouverte
    // alors que l'ancien cookie est en cours de vérification), le jeton obtenu par la
    // connexion est plus récent : un échec ici ne doit pas le déconnecter.
    const startedAt = lastTokenAt
    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        const r = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST' })
        if (r.ok) {
          accessToken = ((await r.json()) as { access_token: string }).access_token
          lastTokenAt = Date.now()
          return true
        }
        if (r.status !== 401) break
        // Un autre onglet vient peut-être de renouveler la session (le cookie a
        // changé entre-temps) : un second essai utilise le nouveau cookie.
        if (attempt === 0) await sleep(300)
      }
      if (lastTokenAt !== startedAt) return true
      accessToken = null
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

export async function login(email: string, password: string): Promise<void> {
  // Format formulaire OAuth2 attendu par l'API (champ « username » = e-mail).
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })
  if (!r.ok) throw await toApiError(r)
  accessToken = ((await r.json()) as { access_token: string }).access_token
  lastTokenAt = Date.now()
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST' })
  } finally {
    accessToken = null
  }
}

// --- Requêtes ----------------------------------------------------------------------

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  /** false : ne pas envoyer X-Company-Id (routes indépendantes de la société). */
  withCompany?: boolean
  /** Société à utiliser pour cette requête (par défaut : la société courante mémorisée). */
  companyId?: number | null
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const send = () => {
    const headers: Record<string, string> = {}
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`
    const companyId = options.companyId !== undefined ? options.companyId : getCompanyId()
    if (options.withCompany !== false && companyId !== null) {
      headers['X-Company-Id'] = String(companyId)
    }
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    return fetch(`${API_BASE}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  }

  let response = await send()
  if (response.status === 401) {
    // Jeton d'accès expiré (ou absent après un rechargement) : on le renouvelle
    // une fois, puis on rejoue la requête.
    if (await refreshAccessToken()) {
      response = await send()
    } else {
      onSessionExpired?.()
    }
  }
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

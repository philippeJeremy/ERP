// Types des réponses de l'API (reflet des schémas Pydantic du backend).

export interface RoleRef {
  id: number
  code: string
  name: string
}

export interface UserRead {
  id: number
  email: string
  full_name: string
  is_active: boolean
  is_superuser: boolean
  last_login_at: string | null
}

export interface Me {
  user: UserRead
  companies: { company_id: number; roles: RoleRef[] }[]
  current_company_id: number | null
  permissions: string[]
  /** Délai d'inactivité après lequel la session est fermée. */
  session_idle_minutes: number
}

export interface Company {
  id: number
  code: string
  name: string
  legal_form: string | null
  siren: string | null
  vat_number: string | null
  city: string | null
  country_code: string
  currency: string
  is_active: boolean
  version: number
}

export interface SessionInfo {
  id: string
  started_at: string
  last_used_at: string
  expires_at: string
  user_agent: string | null
  current: boolean
}

export interface UserInCompany extends UserRead {
  roles: RoleRef[]
  /** Le compte a aussi accès à d'autres sociétés. */
  multi_company: boolean
}

export interface Role {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  permissions: string[]
  user_count: number
}

export interface PermissionInfo {
  code: string
  label: string
}

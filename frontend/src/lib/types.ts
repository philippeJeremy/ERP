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

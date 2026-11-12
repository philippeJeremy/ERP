import { createContext } from 'react'

import type { Company, Me } from '@/lib/types'

export type Status = 'loading' | 'anonymous' | 'authenticated'

export interface AuthContextValue {
  status: Status
  me: Me | undefined
  companies: Company[]
  company: Company | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  selectCompany: (id: number) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

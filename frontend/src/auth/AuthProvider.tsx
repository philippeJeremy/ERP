import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { AuthContext, type AuthContextValue, type Status } from '@/auth/context'
import * as client from '@/lib/api'
import type { Company, Me } from '@/lib/types'

/**
 * État de connexion de toute l'application.
 *
 * Au chargement : on tente de récupérer un jeton d'accès avec le cookie de session.
 * Si ça marche, l'utilisateur est connecté (il avait déjà ouvert l'ERP) ; sinon il
 * passe par la page de connexion.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<Status>('loading')
  const [companyId, setCompanyIdState] = useState<number | null>(client.getCompanyId())

  useEffect(() => {
    client.setSessionExpiredHandler(() => {
      queryClient.clear()
      setStatus('anonymous')
    })
    client.refreshAccessToken().then((ok) => setStatus(ok ? 'authenticated' : 'anonymous'))
  }, [queryClient])

  const authenticated = status === 'authenticated'

  // 1) Les sociétés accessibles (sans en-tête X-Company-Id).
  const companiesQuery = useQuery({
    queryKey: ['companies'],
    queryFn: () => client.api<Company[]>('/org/companies', { withCompany: false }),
    enabled: authenticated,
  })
  const companies = useMemo(() => companiesQuery.data ?? [], [companiesQuery.data])

  // 2) Société courante : celle mémorisée si elle est toujours accessible, sinon la première.
  //    Calculée pendant le rendu (pas de state en double), puis mémorisée pour les requêtes.
  const company = companies.find((c) => c.id === companyId) ?? companies[0] ?? null
  useEffect(() => {
    if (companiesQuery.data) client.setCompanyId(company?.id ?? null)
  }, [companiesQuery.data, company])
  const companyReady = !!companiesQuery.data && (company !== null || companies.length === 0)

  // 3) L'utilisateur et ses permissions DANS la société courante.
  const meQuery = useQuery({
    queryKey: ['me', company?.id ?? null],
    queryFn: () => client.api<Me>('/auth/me', { companyId: company?.id ?? null }),
    enabled: authenticated && companyReady,
  })

  const login = useCallback(async (email: string, password: string) => {
    await client.login(email, password)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    await client.logout()
    queryClient.clear()
    setStatus('anonymous')
  }, [queryClient])

  const selectCompany = useCallback(
    (id: number) => {
      client.setCompanyId(id)
      setCompanyIdState(id)
      // Toutes les données affichées dépendaient de l'ancienne société : on les recharge.
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'companies' })
    },
    [queryClient],
  )

  // « loading » tant que les infos de base ne sont pas arrivées, pour éviter un
  // affichage à moitié rempli.
  const effectiveStatus: Status =
    authenticated && (companiesQuery.isPending || (companyReady && meQuery.isPending)) ? 'loading' : status

  const value: AuthContextValue = {
    status: effectiveStatus,
    me: meQuery.data,
    companies,
    company,
    login,
    logout,
    selectCompany,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

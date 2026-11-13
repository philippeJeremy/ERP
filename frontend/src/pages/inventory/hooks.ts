import { useQuery } from '@tanstack/react-query'

import { useAuth } from '@/auth/useAuth'
import { api } from '@/lib/api'
import type { Location } from '@/pages/inventory/types'
import type { Site } from '@/pages/purchasing/types'

/** Dépôts actifs de la société courante. */
export function useSites() {
  const { company } = useAuth()
  return useQuery({ queryKey: ['sites', company?.id, 'active'], queryFn: () => api<Site[]>('/org/sites?active=true') })
}

/** Emplacements d'un dépôt (le « QUAI » par défaut en premier). */
export function useLocations(siteId: number | null | undefined, active = true) {
  const { company } = useAuth()
  return useQuery({
    queryKey: ['locations', company?.id, siteId, active ? 'active' : 'all'],
    queryFn: () => api<Location[]>(`/inventory/sites/${siteId}/locations${active ? '?active=true' : ''}`),
    enabled: !!siteId,
  })
}

/** Les requêtes à rafraîchir après un mouvement de stock. */
export const STOCK_KEYS = [['stock'], ['article-stock'], ['moves'], ['transfers'], ['counts'], ['count']]

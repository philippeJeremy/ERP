import { ApiError } from '@/lib/api'

/** Message à afficher pour une erreur : celui de l'API quand il existe. */
export function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Une erreur est survenue, réessayez.'
}

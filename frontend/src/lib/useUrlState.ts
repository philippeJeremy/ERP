import { useSearchParams } from 'react-router'

/** Lire / modifier plusieurs paramètres de l'URL d'un coup (valeur vide = paramètre retiré). */
export function useUrlState() {
  const [params, setParams] = useSearchParams()
  const update = (changes: Record<string, string | null | undefined>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === undefined || v === '') next.delete(k)
          else next.set(k, v)
        }
        return next
      },
      { replace: true },
    )
  return [params, update] as const
}

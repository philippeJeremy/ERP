import { useEffect, useState } from 'react'

/** Valeur qui ne change qu'après `delay` ms sans modification : une requête par pause, pas par touche. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

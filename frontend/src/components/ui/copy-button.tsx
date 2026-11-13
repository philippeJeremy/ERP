import { Check, Copy, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type State = 'idle' | 'copied' | 'error'

/**
 * Bouton « copier » avec confirmation visible : une bulle « Copié » s'affiche
 * au-dessus du bouton pendant 2 secondes (et est lue par les lecteurs d'écran).
 */
export function CopyButton({ value, label = 'Copier' }: { value: string; label?: string }) {
  const [state, setState] = useState<State>('idle')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = async () => {
    window.clearTimeout(timer.current)
    try {
      // L'API presse-papiers n'existe qu'en HTTPS (ou sur localhost).
      await navigator.clipboard.writeText(value)
      setState('copied')
    } catch {
      setState('error')
    }
    timer.current = window.setTimeout(() => setState('idle'), 2000)
  }

  const Icon = state === 'copied' ? Check : state === 'error' ? X : Copy
  return (
    <span className="relative inline-flex">
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={copy}
        aria-label={label}
        title={label}
        className={cn(state === 'copied' && 'border-emerald-500/50 text-emerald-700')}
      >
        <Icon />
      </Button>
      <span
        role="status"
        aria-live="polite"
        className={cn(
          'pointer-events-none absolute -top-9 right-0 rounded-md px-2 py-1 text-xs font-medium whitespace-nowrap shadow-md transition-all duration-150',
          state === 'idle' ? 'translate-y-1 opacity-0' : 'translate-y-0 opacity-100',
          state === 'error' ? 'bg-destructive text-white' : 'bg-foreground text-background',
        )}
      >
        {state === 'copied' && 'Copié dans le presse-papiers'}
        {state === 'error' && 'Copie impossible : sélectionnez le texte'}
      </span>
    </span>
  )
}

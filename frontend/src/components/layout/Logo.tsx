import { cn } from '@/lib/utils'

/** Marque de l'ERP : trois traits, comme les lignes d'un document. */
export function Logo({ className, inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-semibold tracking-tight', className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="7" className={inverted ? 'fill-white/10' : 'fill-primary'} />
        <path d="M9 9h14M9 16h10M9 23h14" stroke="#f59e0b" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <span>ERP</span>
    </span>
  )
}

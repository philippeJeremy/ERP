import { cn } from '@/lib/utils'

// Couleurs de l'étiquette européenne des pneus (A = vert foncé … E = rouge).
const COLORS: Record<string, string> = {
  A: 'bg-emerald-600',
  B: 'bg-lime-500',
  C: 'bg-yellow-400 text-yellow-950',
  D: 'bg-orange-400',
  E: 'bg-red-500',
}

function Letter({ value, title }: { value: string | null; title: string }) {
  if (!value) return <span className="inline-flex size-5 items-center justify-center rounded text-[10px] text-muted-foreground ring-1 ring-border">–</span>
  return (
    <span title={`${title} : ${value}`} className={cn('inline-flex size-5 items-center justify-center rounded text-[11px] font-bold text-white', COLORS[value] ?? 'bg-secondary')}>
      {value}
    </span>
  )
}

/** Étiquette UE en version compacte : carburant, adhérence, bruit. */
export function EuLabel({ fuel, wet, noise }: { fuel: string | null; wet: string | null; noise: number | null }) {
  if (!fuel && !wet && !noise) return <span className="text-muted-foreground">—</span>
  return (
    <span className="inline-flex items-center gap-1" aria-label={`Étiquette UE : carburant ${fuel ?? '?'}, adhérence ${wet ?? '?'}, bruit ${noise ?? '?'} dB`}>
      <Letter value={fuel} title="Carburant" />
      <Letter value={wet} title="Adhérence sur sol mouillé" />
      {noise && <span className="text-xs text-muted-foreground tabular-nums">{noise} dB</span>}
    </span>
  )
}

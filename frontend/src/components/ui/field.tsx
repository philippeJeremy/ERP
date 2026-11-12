import { AlertCircle } from 'lucide-react'
import type { ReactNode } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/** Un champ de formulaire : libellé, contrôle, aide et message d'erreur. */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertDescription>{errorMessage(error)}</AlertDescription>
    </Alert>
  )
}

/** Case à cocher avec libellé et description (rôles, permissions). */
export function CheckRow({
  checked,
  onChange,
  disabled,
  title,
  description,
  className,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  title: ReactNode
  description?: ReactNode
  className?: string
}) {
  return (
    <label
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3 text-sm transition-colors',
        disabled ? 'opacity-60' : 'cursor-pointer hover:bg-secondary/60',
        checked && 'border-primary/40 bg-secondary/60',
        className,
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 accent-[var(--primary)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="min-w-0">
        <span className="block font-medium">{title}</span>
        {description && <span className="block text-xs text-muted-foreground">{description}</span>}
      </span>
    </label>
  )
}

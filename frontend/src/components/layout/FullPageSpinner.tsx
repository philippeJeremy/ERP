import { LoaderCircle } from 'lucide-react'

export function FullPageSpinner() {
  return (
    <div className="flex min-h-svh items-center justify-center text-muted-foreground">
      <LoaderCircle className="size-6 animate-spin" aria-label="Chargement" />
    </div>
  )
}

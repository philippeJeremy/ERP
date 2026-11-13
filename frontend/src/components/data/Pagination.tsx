import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'

/** « 26–50 sur 132 articles » + page précédente / suivante. */
export function Pagination({
  page,
  pageSize,
  total,
  noun,
  onPage,
}: {
  page: number // à partir de 0
  pageSize: number
  total: number
  noun: [string, string] // singulier, pluriel
  onPage: (page: number) => void
}) {
  if (total === 0) return null
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const first = page * pageSize + 1
  const last = Math.min(total, (page + 1) * pageSize)
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
      <span>
        {first}–{last} sur {total.toLocaleString('fr-FR')} {total > 1 ? noun[1] : noun[0]}
      </span>
      {pages > 1 && (
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Page précédente" disabled={page === 0} onClick={() => onPage(page - 1)}>
            <ChevronLeft />
          </Button>
          <span className="px-2">
            Page {page + 1} / {pages}
          </span>
          <Button variant="outline" size="icon" aria-label="Page suivante" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)}>
            <ChevronRight />
          </Button>
        </div>
      )}
    </div>
  )
}

import { Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Logo } from '@/components/layout/Logo'
import { Sidebar } from '@/components/layout/Sidebar'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const COLLAPSED_KEY = 'erp.sidebarCollapsed'

/** Cadre des pages connectées : barre latérale (tiroir sur mobile) + contenu. */
export function AppLayout() {
  const { company } = useAuth()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1')
  const [mobileOpen, setMobileOpen] = useState(false)

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSED_KEY, c ? '0' : '1')
      return !c
    })
  }

  // Échap ferme le tiroir mobile.
  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMobileOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])

  return (
    <div className="min-h-svh lg:flex">
      {/* Bureau : barre latérale fixe */}
      <aside
        className={cn(
          'sticky top-0 hidden h-svh shrink-0 transition-[width] duration-200 lg:block',
          collapsed ? 'w-[4.5rem]' : 'w-64',
        )}
      >
        <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
      </aside>

      {/* Mobile : barre du haut + tiroir */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-card/90 px-4 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="-ml-1.5 rounded-md p-1.5 hover:bg-secondary"
          aria-label="Ouvrir le menu"
        >
          <Menu className="size-5" />
        </button>
        <Logo />
      </header>
      <div
        className={cn('fixed inset-0 z-40 lg:hidden', mobileOpen ? 'visible' : 'invisible')}
        aria-hidden={!mobileOpen}
      >
        <div
          className={cn('absolute inset-0 bg-black/50 transition-opacity', mobileOpen ? 'opacity-100' : 'opacity-0')}
          onClick={() => setMobileOpen(false)}
        />
        <div
          className={cn(
            'absolute inset-y-0 left-0 w-72 max-w-[85vw] shadow-xl transition-transform duration-200',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <Sidebar collapsed={false} onNavigate={() => setMobileOpen(false)} />
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="absolute top-3.5 right-3 rounded-md p-1.5 text-sidebar-muted hover:bg-sidebar-accent hover:text-white"
            aria-label="Fermer le menu"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 lg:py-10">
          {company ? (
            <Outlet />
          ) : (
            <Card className="mx-auto max-w-md">
              <CardHeader>
                <CardTitle>Aucune société accessible</CardTitle>
                <CardDescription>
                  Votre compte n'a encore accès à aucune société. Demandez à un administrateur de vous attribuer un
                  rôle.
                </CardDescription>
              </CardHeader>
            </Card>
          )}
        </div>
      </main>
    </div>
  )
}

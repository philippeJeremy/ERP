import { Check, ChevronsUpDown, LogOut, PanelLeftClose, PanelLeftOpen, UserRound } from 'lucide-react'
import { Link, NavLink } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { NAVIGATION, type NavItem } from '@/components/layout/nav'
import { Logo } from '@/components/layout/Logo'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { initials } from '@/lib/format'
import { can } from '@/lib/permissions'
import { cn } from '@/lib/utils'

interface SidebarProps {
  collapsed: boolean
  /** Absent sur mobile (le tiroir se ferme autrement). */
  onToggleCollapsed?: () => void
  /** Appelé après un clic sur un lien (ferme le tiroir sur mobile). */
  onNavigate?: () => void
}

export function Sidebar({ collapsed, onToggleCollapsed, onNavigate }: SidebarProps) {
  const { me } = useAuth()
  const perms = me?.permissions

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      {/* En-tête : logo + bouton replier */}
      <div className={cn('flex h-14 shrink-0 items-center px-4', collapsed ? 'justify-center' : 'justify-between')}>
        {!collapsed && <Logo inverted />}
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
            aria-label={collapsed ? 'Déplier le menu' : 'Replier le menu'}
            title={collapsed ? 'Déplier le menu' : 'Replier le menu'}
          >
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          </button>
        )}
      </div>

      <div className="px-3 pb-2">
        <CompanySwitcher collapsed={collapsed} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-3" aria-label="Navigation principale">
        {NAVIGATION.filter((s) => !s.permission || can(perms, s.permission)).map((section, i) => (
          <div key={section.title ?? i} className="space-y-0.5">
            {section.title &&
              (collapsed ? (
                <div className="mx-auto mb-2 h-px w-6 bg-sidebar-border" />
              ) : (
                <p className="mb-1.5 px-2.5 text-[11px] font-medium tracking-wider text-sidebar-muted uppercase">
                  {section.title}
                </p>
              ))}
            {section.items
              .filter((item) => !item.permission || can(perms, item.permission))
              .map((item) => (
                <SidebarLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
              ))}
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <UserMenu collapsed={collapsed} onNavigate={onNavigate} />
      </div>
    </div>
  )
}

function SidebarLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const Icon = item.icon
  const base = cn(
    'group relative flex h-9 items-center gap-3 rounded-md px-2.5 text-sm transition-colors',
    collapsed && 'justify-center px-0',
  )

  if (item.soon) {
    return (
      <span
        className={cn(base, 'cursor-default text-sidebar-muted/70')}
        title={collapsed ? `${item.label} (bientôt)` : 'Module en cours de développement'}
        aria-disabled
      >
        <Icon className="size-4 shrink-0" />
        {!collapsed && (
          <>
            <span className="truncate">{item.label}</span>
            <span className="ml-auto rounded bg-sidebar-accent px-1.5 py-px text-[10px] text-sidebar-muted">
              bientôt
            </span>
          </>
        )}
      </span>
    )
  }

  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          base,
          isActive
            ? 'bg-sidebar-accent font-medium text-white'
            : 'text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-white',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Repère ambre de l'entrée active */}
          {isActive && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" aria-hidden />}
          <Icon className={cn('size-4 shrink-0', isActive && 'text-accent')} />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </>
      )}
    </NavLink>
  )
}

function CompanySwitcher({ collapsed }: { collapsed: boolean }) {
  const { companies, company, selectCompany } = useAuth()
  if (!company) return null

  const badge = (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent/90 text-xs font-semibold text-accent-foreground">
      {company.code.slice(0, 2)}
    </span>
  )
  const trigger = (
    <button
      type="button"
      disabled={companies.length < 2}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-lg border border-sidebar-border bg-sidebar-accent/40 p-1.5 text-left transition-colors enabled:hover:bg-sidebar-accent',
        collapsed && 'justify-center border-transparent bg-transparent p-0',
      )}
      title={collapsed ? company.name : undefined}
      aria-label={`Société courante : ${company.name}`}
    >
      {badge}
      {!collapsed && (
        <>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-white">{company.name}</span>
            <span className="block truncate text-xs text-sidebar-muted">{company.code}</span>
          </span>
          {companies.length > 1 && <ChevronsUpDown className="size-4 shrink-0 text-sidebar-muted" />}
        </>
      )}
    </button>
  )
  if (companies.length < 2) return trigger

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent side={collapsed ? 'right' : 'bottom'} align="start" className="w-64">
        <DropdownMenuLabel>Changer de société</DropdownMenuLabel>
        {companies.map((c) => (
          <DropdownMenuItem key={c.id} onSelect={() => selectCompany(c.id)}>
            <span className="flex size-6 items-center justify-center rounded bg-secondary text-[10px] font-semibold">
              {c.code.slice(0, 2)}
            </span>
            <span className="min-w-0 flex-1 truncate">{c.name}</span>
            {c.id === company.id && <Check className="text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function UserMenu({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { me, logout } = useAuth()
  const user = me?.user

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex w-full items-center gap-2.5 rounded-lg p-1.5 text-left transition-colors hover:bg-sidebar-accent',
            collapsed && 'justify-center p-0',
          )}
          aria-label="Menu utilisateur"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-xs font-semibold text-white ring-1 ring-sidebar-border">
            {initials(user?.full_name)}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-white">{user?.full_name}</span>
                <span className="block truncate text-xs text-sidebar-muted">{user?.email}</span>
              </span>
              <ChevronsUpDown className="size-4 shrink-0 text-sidebar-muted" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side={collapsed ? 'right' : 'top'} align="start" className="w-60">
        <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
        <DropdownMenuItem asChild>
          <Link to="/profil" onClick={onNavigate}>
            <UserRound /> Mon profil
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={() => void logout()}>
          <LogOut /> Se déconnecter
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

import {
  Boxes,
  Building2,
  LayoutDashboard,
  ReceiptText,
  ShieldCheck,
  ShoppingCart,
  Truck,
  Users,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** Permission nécessaire pour voir l'entrée (règle « module:action »). */
  permission?: string
  /** Module pas encore développé : affiché grisé, avec « bientôt ». */
  soon?: boolean
}

export interface NavSection {
  title?: string
  /** Permission nécessaire pour voir toute la section. */
  permission?: string
  items: NavItem[]
}

/** Le menu de l'ERP. Ajouter un module = ajouter une entrée ici (et sa route). */
export const NAVIGATION: NavSection[] = [
  { items: [{ label: 'Accueil', to: '/', icon: LayoutDashboard }] },
  {
    title: 'Gestion',
    items: [
      { label: 'Tiers', to: '/tiers', icon: Users, soon: true },
      { label: 'Ventes', to: '/ventes', icon: ShoppingCart, soon: true },
      { label: 'Achats', to: '/achats', icon: Truck, soon: true },
      { label: 'Stock', to: '/stock', icon: Boxes, soon: true },
      { label: 'Facturation', to: '/facturation', icon: ReceiptText, soon: true },
    ],
  },
  {
    title: 'Administration',
    permission: 'auth:read',
    items: [
      { label: 'Utilisateurs et rôles', to: '/admin/utilisateurs', icon: ShieldCheck },
      { label: 'Société', to: '/admin/societe', icon: Building2, permission: 'org:manage', soon: true },
    ],
  },
]

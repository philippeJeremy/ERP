import {
  Boxes,
  Building2,
  Factory,
  LayoutDashboard,
  Mail,
  Package,
  ReceiptText,
  ShieldCheck,
  ShoppingCart,
  Truck,
  Warehouse,
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
      { label: 'Fournisseurs', to: '/fournisseurs', icon: Factory, permission: 'partners:read' },
      { label: 'Articles', to: '/articles', icon: Package, permission: 'catalog:read' },
      { label: 'Clients', to: '/clients', icon: Users, permission: 'partners:read' },
      { label: 'Ventes', to: '/ventes', icon: ShoppingCart, permission: 'sales:read' },
      { label: 'Achats', to: '/achats', icon: Truck, permission: 'purchasing:read' },
      { label: 'Stock', to: '/stock', icon: Boxes, permission: 'inventory:read' },
      { label: 'Facturation', to: '/facturation', icon: ReceiptText, permission: 'billing:read' },
    ],
  },
  {
    title: 'Administration',
    items: [
      { label: 'Utilisateurs et rôles', to: '/admin/utilisateurs', icon: ShieldCheck, permission: 'auth:read' },
      { label: 'Sociétés', to: '/admin/societes', icon: Building2, permission: 'org:read' },
      { label: 'Dépôts', to: '/admin/depots', icon: Warehouse, permission: 'org:read' },
      { label: 'Messagerie', to: '/admin/messagerie', icon: Mail, permission: 'mail:read' },
    ],
  },
]

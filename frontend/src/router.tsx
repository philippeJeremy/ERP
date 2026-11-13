import { createBrowserRouter } from 'react-router'

import { RequireAuth } from '@/auth/RequireAuth'
import { AppLayout } from '@/components/layout/AppLayout'
import { CompaniesPage } from '@/pages/admin/CompaniesPage'
import { UsersAdminPage } from '@/pages/admin/UsersAdminPage'
import { ForcePasswordPage } from '@/pages/ForcePasswordPage'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ArticlePage } from '@/pages/catalog/ArticlePage'
import { ArticlesPage } from '@/pages/catalog/ArticlesPage'
import { ImportRunPage } from '@/pages/catalog/ImportRunPage'
import { ImportsPage } from '@/pages/catalog/ImportsPage'
import { NewImportPage } from '@/pages/catalog/NewImportPage'
import { CustomerPage } from '@/pages/customers/CustomerPage'
import { CustomersPage } from '@/pages/customers/CustomersPage'
import { OrderPage } from '@/pages/sales/OrderPage'
import { QuotePage } from '@/pages/sales/QuotePage'
import { SalesPage } from '@/pages/sales/SalesPage'
import { BillingPage } from '@/pages/billing/BillingPage'
import { InvoicePage } from '@/pages/billing/InvoicePage'
import { SupplierInvoicePage } from '@/pages/billing/SupplierInvoicePage'
import { CountPage } from '@/pages/inventory/CountPage'
import { StockPage } from '@/pages/inventory/StockPage'
import { SitesPage } from '@/pages/admin/SitesPage'
import { PurchaseOrderPage } from '@/pages/purchasing/PurchaseOrderPage'
import { PurchaseOrdersPage } from '@/pages/purchasing/PurchaseOrdersPage'
import { SupplierPage } from '@/pages/partners/SupplierPage'
import { SuppliersPage } from '@/pages/partners/SuppliersPage'
import { ProfilePage } from '@/pages/ProfilePage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    // Tout ce qui est sous RequireAuth exige une session.
    element: <RequireAuth />,
    children: [
      { path: 'changer-mot-de-passe', element: <ForcePasswordPage /> },
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <HomePage /> },
          { path: 'profil', element: <ProfilePage /> },
          { path: 'fournisseurs', element: <SuppliersPage /> },
          { path: 'fournisseurs/:id', element: <SupplierPage /> },
          { path: 'articles', element: <ArticlesPage /> },
          { path: 'clients', element: <CustomersPage /> },
          { path: 'clients/:id', element: <CustomerPage /> },
          { path: 'ventes', element: <SalesPage /> },
          { path: 'ventes/devis/:id', element: <QuotePage /> },
          { path: 'ventes/commandes/:id', element: <OrderPage /> },
          { path: 'facturation', element: <BillingPage /> },
          { path: 'facturation/factures/:id', element: <InvoicePage /> },
          { path: 'facturation/fournisseurs/:id', element: <SupplierInvoicePage /> },
          { path: 'achats', element: <PurchaseOrdersPage /> },
          { path: 'achats/:id', element: <PurchaseOrderPage /> },
          { path: 'admin/depots', element: <SitesPage /> },
          { path: 'stock', element: <StockPage /> },
          { path: 'stock/inventaires/:id', element: <CountPage /> },
          { path: 'articles/imports', element: <ImportsPage /> },
          { path: 'articles/imports/nouveau', element: <NewImportPage /> },
          { path: 'articles/imports/:id', element: <ImportRunPage /> },
          { path: 'articles/:id', element: <ArticlePage /> },
          { path: 'admin/utilisateurs', element: <UsersAdminPage /> },
          { path: 'admin/societes', element: <CompaniesPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])

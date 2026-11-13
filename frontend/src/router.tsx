import { createBrowserRouter } from 'react-router'

import { RequireAuth } from '@/auth/RequireAuth'
import { AppLayout } from '@/components/layout/AppLayout'
import { CompaniesPage } from '@/pages/admin/CompaniesPage'
import { UsersAdminPage } from '@/pages/admin/UsersAdminPage'
import { ForcePasswordPage } from '@/pages/ForcePasswordPage'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
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
          { path: 'admin/utilisateurs', element: <UsersAdminPage /> },
          { path: 'admin/societes', element: <CompaniesPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])

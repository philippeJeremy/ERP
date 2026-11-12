# Frontend de l'ERP

React 19 + TypeScript, Vite, Tailwind CSS 4, composants [shadcn/ui](https://ui.shadcn.com)
(copiés dans `src/components/ui`, modifiables), TanStack Query, React Hook Form + Zod,
React Router.

## Développement

```bash
npm install
npm run dev        # http://localhost:5173 (l'API doit tourner : docker compose up -d)
```

Vite transmet `/api/*` à l'API locale (`http://127.0.0.1:8000`) en retirant `/api`,
exactement comme Caddy en production : même origine partout, le cookie de session
fonctionne sans configuration.

Ajouter un composant shadcn : `npx shadcn@latest add select` (voir `components.json`).

## Organisation

```
src/
├── main.tsx              point d'entrée : QueryClient, AuthProvider, routeur
├── router.tsx            les routes (tout ce qui est sous RequireAuth exige une session)
├── lib/api.ts            client HTTP : jetons, X-Company-Id, renouvellement automatique
├── lib/types.ts          types des réponses de l'API
├── auth/                 état de connexion (AuthProvider, useAuth, RequireAuth)
├── components/ui/        composants shadcn/ui
├── components/layout/    cadre de l'application : AppLayout, Sidebar, nav.ts (le menu)
└── pages/                une page = un fichier (accueil, profil, connexion…)
```

## Ajouter une page au menu

1. Créer la page dans `src/pages/`.
2. Ajouter sa route dans `src/router.tsx` (sous `AppLayout`).
3. Ajouter l'entrée dans `src/components/layout/nav.ts`, avec la `permission` requise :
   elle est masquée pour les utilisateurs qui n'ont pas ce droit (l'API contrôle
   quand même chaque requête).

La barre latérale se replie (état mémorisé dans le navigateur) et devient un tiroir
sur mobile.

## Sessions et sécurité

- **Jeton d'accès** (15 min) : en mémoire uniquement, jamais dans `localStorage`.
- **Refresh token** (7 jours) : cookie `httpOnly`, `Secure`, `SameSite=Strict`,
  limité à `/api/auth`. JavaScript ne peut pas le lire.
- À chaque rechargement de page, `refreshAccessToken()` redemande un jeton d'accès.
  Quand une requête reçoit un 401, le jeton est renouvelé puis la requête rejouée.
- Le refresh token change à chaque utilisation (rotation) ; un ancien jeton rejoué
  plus tard révoque toute la session (vol détecté).
- **Déconnexion automatique** (`auth/useIdleLogout.ts`) : sans activité (souris,
  clavier, tactile) dans aucun onglet pendant le délai fixé par l'API (30 min), la
  session est fermée et l'écran revient à la connexion, avec un message. Un
  utilisateur actif sans requête (longue saisie) voit sa session renouvelée en
  arrière-plan. Durée maximale : 12 h, imposée par l'API.
- En production, Caddy ajoute une `Content-Security-Policy` stricte : seuls les
  scripts servis par le domaine s'exécutent.

## Scripts

| Commande | Rôle |
|---|---|
| `npm run dev` | Serveur de développement |
| `npm run build` | Vérification des types + build de production (`dist/`) |
| `npm run lint` | Lint (oxlint) |

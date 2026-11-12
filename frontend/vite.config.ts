import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // « @/components/ui/button » au lieu de « ../../components/ui/button »
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    // Un seul paquet JS pour l'instant (~160 ko compressé) : on découpera par module
    // métier (import() dynamique) quand l'application grossira.
    chunkSizeWarningLimit: 700,
  },
  server: {
    // En développement, le navigateur parle à Vite (http://localhost:5173), qui
    // transmet /api/* à l'API locale en retirant « /api » — exactement comme Caddy
    // en production. Même origine dans les deux cas : le cookie de session
    // (chemin /api/auth) fonctionne pareil partout, sans configuration CORS.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})

import { useEffect } from 'react'

import { getLastTokenAt, refreshAccessToken } from '@/lib/api'

const ACTIVITY_KEY = 'erp.lastActivity'
const EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'] as const
const CHECK_EVERY_MS = 30_000
const WRITE_EVERY_MS = 15_000
const RENEW_AFTER_MS = 10 * 60_000

/** Dernière activité, tous onglets confondus (partagée via localStorage). */
function lastActivity(): number {
  return Number(localStorage.getItem(ACTIVITY_KEY) ?? 0)
}

export function markActivity() {
  localStorage.setItem(ACTIVITY_KEY, String(Date.now()))
}

/**
 * Déconnexion automatique de l'ÉCRAN après inactivité.
 *
 * L'API fait déjà expirer la session après `idleMinutes` sans requête. Mais sans ce
 * hook, un poste laissé ouvert continuerait d'AFFICHER les données jusqu'au prochain
 * clic. Ici :
 *  - toute action (souris, clavier, tactile) compte comme activité, dans n'importe
 *    quel onglet de l'ERP (valeur partagée dans localStorage) ;
 *  - utilisateur actif mais sans requête depuis 10 min (saisie d'un long formulaire) :
 *    on renouvelle la session pour que l'API ne la ferme pas sous ses pieds ;
 *  - plus aucune activité pendant `idleMinutes` : déconnexion.
 */
export function useIdleLogout(idleMinutes: number | undefined, onIdle: () => void) {
  useEffect(() => {
    if (!idleMinutes) return
    const idleMs = idleMinutes * 60_000
    let lastWrite = 0

    const onActivity = () => {
      const now = Date.now()
      if (now - lastWrite > WRITE_EVERY_MS) {
        lastWrite = now
        markActivity()
      }
    }

    const check = () => {
      const now = Date.now()
      const idleFor = now - lastActivity()
      if (idleFor >= idleMs) {
        onIdle()
      } else if (idleFor < 60_000 && now - getLastTokenAt() > RENEW_AFTER_MS) {
        void refreshAccessToken()
      }
    }

    markActivity()
    EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))
    // Au retour sur l'onglet (PC réveillé), on vérifie tout de suite.
    document.addEventListener('visibilitychange', check)
    const timer = window.setInterval(check, CHECK_EVERY_MS)
    return () => {
      EVENTS.forEach((e) => window.removeEventListener(e, onActivity))
      document.removeEventListener('visibilitychange', check)
      window.clearInterval(timer)
    }
  }, [idleMinutes, onIdle])
}

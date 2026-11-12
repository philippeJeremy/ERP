/** Même règle que l'API : permission exacte, « module:* » ou « * ». Sert à masquer
 * ce que l'utilisateur ne peut pas faire ; le vrai contrôle reste fait par l'API. */
export function can(permissions: string[] | undefined, permission: string): boolean {
  if (!permissions) return false
  const module = permission.split(':', 1)[0]
  return permissions.includes(permission) || permissions.includes(`${module}:*`) || permissions.includes('*')
}

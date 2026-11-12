import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Combine des classes Tailwind en résolvant les conflits (« p-2 » + « p-4 » → « p-4 »). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

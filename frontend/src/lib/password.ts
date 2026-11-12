// Sans caractères ambigus (0/O, 1/l/I) : le mot de passe est souvent dicté ou recopié.
const ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'

/** Mot de passe aléatoire de 16 caractères en 4 groupes (≈ 93 bits), tiré avec le
 * générateur cryptographique du navigateur (pas Math.random, qui est prévisible). */
export function generatePassword(): string {
  const chars: string[] = []
  // Tirage sans biais : on rejette les octets au-delà du plus grand multiple de la
  // taille de l'alphabet (sinon les premières lettres sortiraient plus souvent).
  const limit = 256 - (256 % ALPHABET.length)
  while (chars.length < 16) {
    for (const byte of crypto.getRandomValues(new Uint8Array(32))) {
      if (byte < limit && chars.length < 16) chars.push(ALPHABET[byte % ALPHABET.length])
    }
  }
  return [0, 4, 8, 12].map((i) => chars.slice(i, i + 4).join('')).join('-')
}

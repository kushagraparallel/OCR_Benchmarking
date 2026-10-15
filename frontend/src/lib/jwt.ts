interface AccessTokenClaims {
  sub: string
  sid: string
}

// Decodes the unverified payload for display purposes only (e.g. highlighting
// the current session); the server is the sole source of truth for validity.
export function decodeAccessTokenClaims(token: string): AccessTokenClaims | null {
  try {
    const [, payload] = token.split('.')
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const json = JSON.parse(atob(normalized)) as Partial<AccessTokenClaims>
    if (typeof json.sid !== 'string' || typeof json.sub !== 'string') return null
    return { sub: json.sub, sid: json.sid }
  } catch {
    return null
  }
}

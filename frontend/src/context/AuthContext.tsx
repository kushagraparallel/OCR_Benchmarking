import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as authApi from '../api/auth'
import { api, registerUnauthorizedHandler, setAccessToken } from '../lib/apiClient'
import type { User } from '../lib/types'

interface AuthContextValue {
  user: User | null
  status: 'bootstrapping' | 'authenticated' | 'anonymous'
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  logoutAll: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthContextValue['status']>('bootstrapping')

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  useEffect(() => {
    registerUnauthorizedHandler(clearSession)
  }, [clearSession])

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      const token = await api.refreshAccessToken()
      if (!token) {
        if (!cancelled) setStatus('anonymous')
        return
      }
      try {
        const currentUser = await authApi.getCurrentUser()
        if (!cancelled) {
          setUser(currentUser)
          setStatus('authenticated')
        }
      } catch {
        if (!cancelled) clearSession()
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [clearSession])

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password)
    setAccessToken(response.access_token)
    setUser(response.user)
    setStatus('authenticated')
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    await authApi.register(email, password)
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      clearSession()
    }
  }, [clearSession])

  const logoutAll = useCallback(async () => {
    try {
      await authApi.logoutAll()
    } finally {
      clearSession()
    }
  }, [clearSession])

  const value = useMemo(
    () => ({ user, status, login, register, logout, logoutAll }),
    [user, status, login, register, logout, logoutAll],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}

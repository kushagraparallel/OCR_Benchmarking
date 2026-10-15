import { api } from '../lib/apiClient'
import type { MessageResponse, TokenResponse, User } from '../lib/types'

export function register(email: string, password: string): Promise<User> {
  return api.post<User>('/auth/register', { email, password })
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/auth/login', { email, password })
}

export function logout(): Promise<MessageResponse> {
  return api.post<MessageResponse>('/auth/logout')
}

export function logoutAll(): Promise<MessageResponse> {
  return api.post<MessageResponse>('/auth/logout-all')
}

export function getCurrentUser(): Promise<User> {
  return api.get<User>('/auth/me')
}

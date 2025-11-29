import { APIService } from '../lib/api.js'

export function buildAuthSnapshot(detail = {}) {
  const token = detail.token !== undefined ? detail.token : APIService.userToken
  const isAdmin = detail.isAdmin !== undefined ? detail.isAdmin : APIService.isAdmin()
  const isJournalist = detail.isJournalist !== undefined ? detail.isJournalist : APIService.isJournalist()
  const hasApiKey = detail.hasApiKey !== undefined ? detail.hasApiKey : !!APIService.adminKey
  const displayName = detail.displayName !== undefined ? detail.displayName : APIService.displayName
  const displayNameConfirmed = detail.displayNameConfirmed !== undefined ? detail.displayNameConfirmed : APIService.displayNameConfirmed()
  return {
    token,
    isAdmin,
    isJournalist,
    hasApiKey,
    displayName,
    displayNameConfirmed,
    role: detail.role || (isAdmin ? 'admin' : (isJournalist ? 'journalist' : 'user')),
    expiresIn: detail.expiresIn || null,
  }
}

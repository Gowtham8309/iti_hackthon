export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export function parseApiError(detail, fallback = 'Request failed.') {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const f = detail[0]
    return typeof f === 'string' ? f : (f?.msg || fallback)
  }
  if (typeof detail === 'object') return detail.msg || detail.message || fallback
  return fallback
}

export async function apiFetch(path, options = {}, token = null) {
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }
  const resp = await fetch(API_BASE + path, { ...options, headers })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(parseApiError(data.detail, `HTTP ${resp.status}`))
  }
  return data
}

export async function apiFetchBlob(path, options = {}, token = null) {
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }
  const resp = await fetch(API_BASE + path, { ...options, headers })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp
}

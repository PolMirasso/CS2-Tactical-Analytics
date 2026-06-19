// Thin typed fetch wrapper around the FastAPI backend.
//
// Centralises base URL, the JWT bearer header and error normalisation so feature
// code never touches `fetch` directly. As the app grows, interceptors (refresh,
// tracing, etc.) belong here.

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const TOKEN_KEY = 'cs2.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  auth?: boolean
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = opts
  const headers: Record<string, string> = {}

  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body // browser sets multipart boundary
  } else if (body instanceof URLSearchParams) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const resp = await fetch(`${BASE_URL}${path}`, { method, headers, body: payload })

  if (resp.status === 204) return undefined as T

  const text = await resp.text()
  const data = text ? JSON.parse(text) : undefined

  if (!resp.ok) {
    const detail = (data as { detail?: unknown })?.detail
    const message = typeof detail === 'string' ? detail : resp.statusText
    throw new ApiError(resp.status, message)
  }

  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  postForm: <T>(path: string, body: FormData | URLSearchParams, auth = true) =>
    request<T>(path, { method: 'POST', body, auth }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()

export const API_BASE_URL = configuredBaseUrl?.replace(/\/$/, '') ?? ''
export const API_TIMEOUT_MS = 10_000

export const JSON_HEADERS = {
  'Content-Type': 'application/json',
  'ngrok-skip-browser-warning': 'true',
}

let operationCounter = 0

export function operationId(): string {
  operationCounter = (operationCounter + 1) % 0x1000000
  const timestamp = Date.now().toString(36)
  const counter = operationCounter.toString(36)
  const random = Math.floor(Math.random() * 0x100000000).toString(36)
  return `web-${timestamp}-${counter}-${random}`
}

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS)
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: { 'ngrok-skip-browser-warning': 'true', ...init.headers },
      signal: controller.signal,
    })
    if (!response.ok) {
      const detail = await response.text()
      try {
        const parsed = JSON.parse(detail) as { message?: string }
        throw new Error(parsed.message || detail || `Request failed: ${response.status}`)
      } catch (error) {
        if (error instanceof SyntaxError) {
          throw new Error(detail || `Request failed: ${response.status}`)
        }
        throw error
      }
    }
    return response.json() as Promise<T>
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('遊戲伺服器回應逾時，請稍後重新連線。')
    }
    if (error instanceof TypeError) {
      throw new Error('遊戲伺服器目前無法連線。')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export interface HealthView {
  status: 'ok'
  version: string
  database: 'ok'
}

export function getHealth(): Promise<HealthView> {
  return request('/api/health')
}

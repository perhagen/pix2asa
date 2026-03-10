/** API client for the pix2asa FastAPI backend. */

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`HTTP ${res.status}: ${body}`)
  }
  return res.json()
}

/** GET /api/devices → list of device objects */
export function getDevices() {
  return apiFetch('/api/devices')
}

/** GET /api/version → { version: string } */
export function getVersion() {
  return apiFetch('/api/version')
}

/**
 * POST /api/convert
 * @param {{ config: string, target_platform: string, source_version: number,
 *           target_version: number, interface_map: object,
 *           custom_5505: boolean, boot_system: string|null }} payload
 * @returns {{ output: string, log: string, warnings: string[], errors: string[] }}
 */
export function convertConfig(payload) {
  return apiFetch('/api/convert', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

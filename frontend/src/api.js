export const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function makeId() {
  return crypto.randomUUID?.() || `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

// One session per browser tab (kept across refreshes), so two people using the
// live demo at the same time get separate runs on the backend.
function readSessionId() {
  try {
    let id = sessionStorage.getItem('microgrid-session')
    if (!id) { id = makeId(); sessionStorage.setItem('microgrid-session', id) }
    return id
  } catch {
    return makeId()
  }
}

export const SESSION_ID = readSessionId()

export function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...(options.headers || {}), 'X-Session-Id': SESSION_ID },
  })
}

// For plain links (downloads) that can't send a header.
export const sessionUrl = (path) => `${API_URL}${path}?session=${encodeURIComponent(SESSION_ID)}`

export async function checkedJson(res) {
  if (!res.ok) throw new Error(`The backend returned an error (${res.status}). Check the server log.`)
  return res.json()
}

export function errorMessage(err) {
  return err instanceof TypeError
    ? `Can't reach the backend at ${API_URL}. Make sure uvicorn main:app is running.`
    : err.message
}

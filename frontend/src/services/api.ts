// services/api.ts - Typed fetch with same-origin cookies and readable API failures.
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  // Keep error bodies bounded and turn validation arrays into useful form feedback.
  const response = await fetch(`/api${path}`, { method, credentials: 'include',
    headers: body === undefined ? undefined : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item: {msg: string}) => item.msg).join('; ') : data.detail;
    throw new Error(detail || 'Unable to complete this request');
  }
  return data as T;
}

export function clockTime(timestamp: number): string {
  // Sensor and server timestamps use epoch seconds throughout the application.
  return new Date(timestamp * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', second: '2-digit'});
}

export function duration(seconds: number): string {
  // Avoid negative elapsed time while clocks settle after session creation.
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toString().padStart(2, '0')}`;
}

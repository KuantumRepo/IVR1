const API_URL = (process.env.INTERNAL_API_URL || '/api/v1');

/**
 * Get the stored JWT token from localStorage.
 * Returns null on the server side or if no token exists.
 */
function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

/**
 * Build headers with JWT Authorization if token exists.
 */
function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Handle 401 responses globally — redirect to login on token expiry.
 */
function handle401(res: Response): void {
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('auth_token');
    // Avoid redirect loop if already on login page
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
  }
}

/**
 * Authenticated fetch wrapper. Attaches JWT and handles 401 globally.
 * Use this for any direct fetch calls that don't go through the api helper.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = authHeaders(
    options.headers as Record<string, string> | undefined
  );
  
  const res = await fetch(url, { ...options, headers });
  handle401(res);
  return res;
}

export const api = {
  get: async (endpoint: string) => {
    const res = await fetch(`${API_URL}${endpoint}`, {
      headers: authHeaders(),
    });
    handle401(res);
    if (!res.ok) throw new Error(`GET ${endpoint} failed`);
    return res.json();
  },
  
  post: async (endpoint: string, body: any) => {
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body)
    });
    handle401(res);
    if (!res.ok) throw new Error(`POST ${endpoint} failed`);
    return res.json();
  },

  delete: async (endpoint: string) => {
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    handle401(res);
    if (!res.ok) throw new Error(`DELETE ${endpoint} failed`);
    return res.json();
  }
};

/**
 * Global fetch interceptor — patches window.fetch to inject JWT auth headers
 * on all /api/v1 requests. This is a safety net that ensures EVERY fetch call
 * in the app (including those that bypass lib/api.ts) gets authenticated.
 * 
 * Also handles 401 responses globally — redirects to /login on token expiry.
 * 
 * This must be called once at app initialization (in the root layout or provider).
 */

let interceptorInstalled = false;

export function installFetchInterceptor() {
  if (typeof window === 'undefined' || interceptorInstalled) return;
  interceptorInstalled = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;

    // Only intercept /api/v1 calls (not /api/auth or external URLs)
    if (url.includes('/api/v1')) {
      const token = localStorage.getItem('auth_token');
      if (token) {
        const headers = new Headers(init?.headers);
        if (!headers.has('Authorization')) {
          headers.set('Authorization', `Bearer ${token}`);
        }
        init = { ...init, headers };
      }
    }

    const response = await originalFetch(input, init);

    // Global 401 handler — redirect to login if token expired mid-session
    if (response.status === 401 && url.includes('/api/v1')) {
      if (!window.location.pathname.startsWith('/login')) {
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
      }
    }

    return response;
  };
}

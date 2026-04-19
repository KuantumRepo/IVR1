import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Next.js middleware — minimal pass-through.
 * 
 * Auth is now handled by:
 *   - Backend: JWT middleware on all /api/v1/* routes
 *   - Frontend: AuthProvider checks token and redirects to /login
 * 
 * This middleware no longer performs any auth checks.
 */
export default function middleware(request: NextRequest) {
  return NextResponse.next()
}

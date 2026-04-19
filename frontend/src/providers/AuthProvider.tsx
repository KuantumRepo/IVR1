"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { installFetchInterceptor } from "@/lib/fetch-interceptor";

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  isLoading: true,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

const AUTH_API = process.env.NEXT_PUBLIC_API_URL
  ? process.env.NEXT_PUBLIC_API_URL.replace('/v1', '/auth')
  : '/api/auth';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  // Install the global fetch interceptor on mount
  useEffect(() => {
    installFetchInterceptor();
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    setIsAuthenticated(false);
    router.push("/login");
  }, [router]);

  useEffect(() => {
    // Skip verification on login page
    if (pathname === "/login") {
      setIsLoading(false);
      return;
    }

    const verifyToken = async () => {
      const token = localStorage.getItem("auth_token");

      if (!token) {
        setIsAuthenticated(false);
        setIsLoading(false);
        router.push("/login");
        return;
      }

      try {
        const res = await fetch(`${AUTH_API}/verify`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (res.ok) {
          setIsAuthenticated(true);
        } else {
          localStorage.removeItem("auth_token");
          setIsAuthenticated(false);
          router.push("/login");
        }
      } catch {
        // Network error — keep the token, user might be offline temporarily
        setIsAuthenticated(true);
      } finally {
        setIsLoading(false);
      }
    };

    verifyToken();
  }, [pathname, router]);

  // While verifying, show nothing (prevents 401 flood from other components)
  if (isLoading && pathname !== "/login") {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
          <p className="text-white/40 text-xs font-mono tracking-widest uppercase">Verifying access</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

const AUTH_API = process.env.NEXT_PUBLIC_API_URL
  ? process.env.NEXT_PUBLIC_API_URL.replace('/v1', '/auth')
  : '/api/auth';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const totpRef = useRef<HTMLInputElement>(null);

  // Check if already authenticated
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      fetch(`${AUTH_API}/verify`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then(res => {
        if (res.ok) router.push("/");
      }).catch(() => {});
    }
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const res = await fetch(`${AUTH_API}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          totp_code: totpCode,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("auth_token", data.access_token);
        router.push("/");
      } else {
        setError("Invalid credentials");
        setPassword("");
        setTotpCode("");
        setTimeout(() => setError(""), 3000);
      }
    } catch {
      setError("Connection failed");
      setTimeout(() => setError(""), 3000);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 relative overflow-hidden select-none">
      {/* Ambient background */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-emerald-500/[0.07] rounded-full blur-[150px] animate-pulse" style={{ animationDuration: '8s' }} />
        <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] bg-cyan-500/[0.05] rounded-full blur-[150px] animate-pulse" style={{ animationDuration: '12s' }} />
        <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] bg-purple-500/[0.04] rounded-full blur-[120px] animate-pulse" style={{ animationDuration: '10s' }} />
        
        {/* Grid pattern */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: 'linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }}
        />
      </div>

      <div className="w-full max-w-[420px] relative z-10">
        {/* Logo / Identity */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-white/10 to-white/[0.02] border border-white/10 mb-6 shadow-[0_0_40px_rgba(255,255,255,0.05)]">
            <svg className="w-7 h-7 text-white/80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <h1 className="text-[22px] font-semibold text-white tracking-tight mb-1.5">System Access</h1>
          <p className="text-white/30 text-[13px] font-mono tracking-wider">AUTHENTICATION REQUIRED</p>
        </div>

        {/* Form Card */}
        <form onSubmit={handleLogin}>
          <div className="bg-white/[0.03] backdrop-blur-2xl border border-white/[0.07] rounded-2xl p-7 shadow-2xl shadow-black/50 space-y-5">
            
            {/* Username */}
            <div className="space-y-2">
              <label className="text-[11px] font-medium text-white/40 uppercase tracking-widest">Operator</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/15 focus:outline-none focus:border-white/20 focus:bg-white/[0.06] transition-all"
                placeholder="Username"
                autoComplete="username"
                autoFocus
                required
              />
            </div>

            {/* Password */}
            <div className="space-y-2">
              <label className="text-[11px] font-medium text-white/40 uppercase tracking-widest">Access Key</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/15 focus:outline-none focus:border-white/20 focus:bg-white/[0.06] transition-all"
                placeholder="Password"
                autoComplete="current-password"
                required
              />
            </div>

            {/* TOTP Code */}
            <div className="space-y-2">
              <label className="text-[11px] font-medium text-white/40 uppercase tracking-widest">Verification Code</label>
              <input
                ref={totpRef}
                type="text"
                inputMode="numeric"
                maxLength={32}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/15 focus:outline-none focus:border-white/20 focus:bg-white/[0.06] transition-all font-mono tracking-[0.3em] text-center"
                placeholder="000000"
                autoComplete="one-time-code"
                required
              />
              <p className="text-[10px] text-white/20 text-center mt-1">Enter 6-digit authenticator code, or emergency bypass code</p>
            </div>

            {/* Error */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5 text-red-400 text-xs text-center font-medium animate-in fade-in slide-in-from-top-1 duration-200">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-white text-black hover:bg-white/90 disabled:bg-white/50 disabled:cursor-not-allowed px-4 py-3.5 rounded-xl font-semibold text-sm transition-all active:scale-[0.98] shadow-[0_0_30px_rgba(255,255,255,0.08)] flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                  Authenticating...
                </>
              ) : (
                <>
                  Authenticate
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Footer */}
        <div className="text-center mt-8 space-y-1.5">
          <p className="text-[9px] text-white/[0.12] font-mono tracking-[0.25em] uppercase">Proprietary Voice Engine</p>
          <p className="text-[9px] text-white/[0.12] font-mono tracking-[0.25em] uppercase">Authorized Operators Only</p>
        </div>
      </div>
    </div>
  );
}

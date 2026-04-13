"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, ArrowRight } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    // Simple hardcoded security for MVP internal use
    if (password === "broadcaster2026" || password === "admin") {
      document.cookie = "admin_auth=authenticated; path=/; max-age=86400";
      router.push("/");
    } else {
      setError(true);
      setTimeout(() => setError(false), 2000);
      setPassword("");
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background aesthetics */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        <div className="bg-background/80 backdrop-blur-2xl border border-white/10 p-8 rounded-3xl shadow-2xl">
          <div className="flex justify-center mb-8">
            <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center border border-white/10 shadow-inner">
              <Lock className="w-8 h-8 text-emerald-400" />
            </div>
          </div>
          
          <h1 className="text-2xl font-bold text-white text-center mb-2 tracking-tight">System Restricted</h1>
          <p className="text-muted-foreground text-center mb-8 text-sm">Awaiting authentication token to access engine.</p>

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Access Protocol Key"
                className={`w-full bg-black/50 border rounded-xl px-4 py-3.5 text-white focus:outline-none transition-colors text-center tracking-widest
                  ${error ? 'border-red-500/50 bg-red-500/5 text-red-100 placeholder:text-red-500/50' : 'border-white/10 focus:border-emerald-500/50'}`}
                autoFocus
              />
            </div>
            
            <button
              type="submit"
              className="w-full bg-white text-black hover:bg-neutral-200 px-4 py-3.5 rounded-xl font-semibold transition-transform active:scale-95 flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.1)]"
            >
              Unlock Dashboard <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        </div>
        
        <div className="text-center mt-8 space-y-1">
          <p className="text-[10px] text-white/20 font-mono tracking-widest uppercase">Proprietary Voice Engine</p>
          <p className="text-[10px] text-white/20 font-mono tracking-widest uppercase">Internal Node Authorized Personnel Only</p>
        </div>
      </div>
    </div>
  );
}

"use client";

import { Save, ShieldAlert, SlidersHorizontal, UserPlus } from "lucide-react";
import { useState } from "react";

export default function SettingsPage() {
  const [globalDnc, setGlobalDnc] = useState(true);
  const [strictStir, setStrictStir] = useState(false);

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-4xl mx-auto relative z-10">
      
      <div className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Global Settings</h1>
        <p className="text-muted-foreground w-11/12">Manage platform-wide behavioral defaults, DNC (Do Not Call) filters, and Engine compliance restrictions.</p>
      </div>

      <div className="space-y-6">
        
        {/* Compliance Block */}
        <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
           <div className="flex items-center gap-3 mb-6 pb-6 border-b border-white/5">
              <ShieldAlert className="w-5 h-5 text-emerald-400" />
              <h3 className="text-lg font-medium text-white">Compliance & Routing</h3>
           </div>
           
           <div className="space-y-6">
              <div className="flex items-start justify-between gap-4">
                 <div>
                    <h4 className="text-sm font-medium text-white mb-1">Enforce Global DNC Architecture</h4>
                    <p className="text-xs text-muted-foreground">Automatically scrubs all outbound Campaign lists against the global database pool before dial attempts.</p>
                 </div>
                 <button 
                    onClick={() => setGlobalDnc(!globalDnc)}
                    className={`w-12 h-6 rounded-full transition-colors relative ${globalDnc ? 'bg-emerald-500' : 'bg-white/10'}`}
                 >
                    <div className={`absolute top-1 transform transition-transform bg-white w-4 h-4 rounded-full ${globalDnc ? 'translate-x-7' : 'translate-x-1'}`} />
                 </button>
              </div>

              <div className="flex items-start justify-between gap-4 border-t border-white/5 pt-6">
                 <div>
                    <h4 className="text-sm font-medium text-white mb-1">Strict STIR/SHAKEN Validation</h4>
                    <p className="text-xs text-muted-foreground">Drop outbound dials if the internal gateway cannot authenticate the Caller ID via A-level attestation.</p>
                 </div>
                 <button 
                    onClick={() => setStrictStir(!strictStir)}
                    className={`w-12 h-6 rounded-full transition-colors relative ${strictStir ? 'bg-emerald-500' : 'bg-white/10'}`}
                 >
                    <div className={`absolute top-1 transform transition-transform bg-white w-4 h-4 rounded-full ${strictStir ? 'translate-x-7' : 'translate-x-1'}`} />
                 </button>
              </div>
           </div>
        </div>

        {/* Engine Tuning Defaults */}
        <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
           <div className="flex items-center gap-3 mb-6 pb-6 border-b border-white/5">
              <SlidersHorizontal className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-medium text-white">Default Engine Tuning</h3>
           </div>
           
           <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
              <div>
                 <label className="text-xs font-semibold text-muted-foreground uppercase tracking-widest block mb-2">Globally Capped CPS</label>
                 <input type="number" defaultValue={50} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 text-sm text-white focus:border-purple-500 transition-colors focus:outline-none" />
                 <p className="text-[10px] text-muted-foreground mt-2">Maximum allowed calls-per-second across all running campaigns combined.</p>
              </div>
              <div>
                 <label className="text-xs font-semibold text-muted-foreground uppercase tracking-widest block mb-2">TTS Neural Worker Threads</label>
                 <select className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 text-sm text-white focus:border-purple-500 transition-colors focus:outline-none appearance-none">
                    <option>4 Dedicated Threads (CPU)</option>
                    <option>8 Dedicated Threads (CPU)</option>
                    <option>VRAM Acceleration (CUDA)</option>
                 </select>
                 <p className="text-[10px] text-muted-foreground mt-2">Maximum parallel instances of the Kokoro text-to-speech models allocated.</p>
              </div>
           </div>
        </div>

      </div>

      <div className="mt-8 flex justify-end">
         <button className="bg-white text-black hover:bg-neutral-200 px-8 py-3 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
            <Save className="w-4 h-4" />
            Commit Configuration
         </button>
      </div>

    </div>
  );
}

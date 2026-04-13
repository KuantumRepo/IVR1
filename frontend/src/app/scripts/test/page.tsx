"use client";

import { useState } from "react";
import { ArrowLeft, PlayCircle, Settings2, Target } from "lucide-react";
import Link from "next/link";

export default function ScriptTestWizard() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [formData, setFormData] = useState({
     ring_timeout: 45,
     gateway_connect_timeout: 30,
     dial_timeout: 60,
     vocal_pause: 2.0,
     idle_looping_delay: 5,
     max_idle_loops: 3,
     max_stage_transitions: 20
  });

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-4xl mx-auto relative z-10">
      
      <div className="mb-10">
        <Link href="/scripts" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-white transition-colors mb-6">
           <ArrowLeft className="w-4 h-4" /> Back to Scripts
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Test Call Script</h1>
        <p className="text-muted-foreground">Manually originate a dedicated test execution pinging your specific sequence through the FreeSWITCH backbone.</p>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl relative overflow-hidden">
         <div className="space-y-6">
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               <div>
                  <label className="text-sm font-medium text-white mb-2 block">Target Call Script</label>
                  <select className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                     <option>-- Select Call Script --</option>
                     <option>B2B Solar Press-1 (Female Accent)</option>
                  </select>
               </div>
               <div>
                  <label className="text-sm font-medium text-white mb-2 block">SIP Gateway Trunk</label>
                  <select className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                     <option>-- Select Routing Gateway --</option>
                     <option>CAD-USA</option>
                  </select>
               </div>
               <div>
                  <label className="text-sm font-medium text-white mb-2 block">Routing Agent</label>
                  <select className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                     <option>-- Select a Live Agent --</option>
                  </select>
               </div>
               <div>
                  <label className="text-sm font-medium text-white mb-2 block">Outbound Caller ID</label>
                  <select className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                     <option>-- Masking Profiles --</option>
                  </select>
               </div>
            </div>

            <hr className="border-white/5 my-4" />

            <div>
               <label className="text-sm font-medium text-white mb-2 block">Destination Phone Number</label>
               <input type="text" className="w-full max-w-sm bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-emerald-500 font-mono transition-colors" placeholder="+1 (555) 000-0000" />
            </div>

            <div>
               <label className="text-sm font-medium text-white mb-2 block">DNC Scrubbing List</label>
               <select className="w-full max-w-sm bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                  <option>Global DNC</option>
               </select>
            </div>

            <div className="space-y-4 pt-4">
               <label className="flex items-center gap-3 cursor-pointer">
                 <input type="checkbox" defaultChecked className="w-4 h-4 rounded text-emerald-500 bg-white/10 border-white/20 focus:ring-emerald-500/20" />
                 <span className="text-sm text-white">Enable voicemail detection</span>
               </label>
               <label className="flex items-center gap-3 cursor-pointer">
                 <input type="checkbox" defaultChecked className="w-4 h-4 rounded text-emerald-500 bg-white/10 border-white/20 focus:ring-emerald-500/20" />
                 <span className="text-sm text-white">Hangup on voicemail</span>
               </label>
               <label className="flex items-center gap-3 cursor-pointer">
                 <input type="checkbox" className="w-4 h-4 rounded text-emerald-500 bg-white/10 border-white/20 focus:ring-emerald-500/20" />
                 <span className="text-sm text-white">Use legacy DTMF detection</span>
               </label>
            </div>

            {/* Advanced Toggle */}
            <div className="pt-6 border-t border-white/5">
                <button 
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="flex items-center gap-2 text-emerald-400 text-sm font-medium hover:text-emerald-300 transition-colors"
                >
                   <Settings2 className="w-4 h-4" /> {showAdvanced ? 'Hide Advanced Configs' : 'Show Advanced Timing Constants'}
                </button>

                {showAdvanced && (
                    <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-6 bg-black/20 p-6 rounded-xl border border-white/5 animate-in fade-in slide-in-from-top-2">
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Ring timeout</label>
                         <input type="number" value={formData.ring_timeout} onChange={e => setFormData({...formData, ring_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Gateway connect timeout</label>
                         <input type="number" value={formData.gateway_connect_timeout} onChange={e => setFormData({...formData, gateway_connect_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Dial timeout</label>
                         <input type="number" value={formData.dial_timeout} onChange={e => setFormData({...formData, dial_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Vocal pause between plays</label>
                         <input type="number" step="0.5" value={formData.vocal_pause} onChange={e => setFormData({...formData, vocal_pause: parseFloat(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Idle looping delay</label>
                         <input type="number" value={formData.idle_looping_delay} onChange={e => setFormData({...formData, idle_looping_delay: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Maximum idle loops</label>
                         <input type="number" value={formData.max_idle_loops} onChange={e => setFormData({...formData, max_idle_loops: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Maximum stage transitions</label>
                         <input type="number" value={formData.max_stage_transitions} onChange={e => setFormData({...formData, max_stage_transitions: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                    </div>
                )}
            </div>

            <div className="pt-8 flex justify-end">
               <button className="bg-emerald-500 text-black shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:bg-emerald-400 px-8 py-3.5 rounded-lg font-semibold transition-transform active:scale-95 flex items-center gap-2">
                  <PlayCircle className="w-5 h-5" /> Launch Single Dispatch Ping
               </button>
            </div>

         </div>
      </div>
    </div>
  );
}

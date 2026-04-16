"use client";

import { useEffect, useState, use, useCallback, useRef } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Pause, Square, Activity, Play, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useWebSocket } from "@/providers/WebSocketProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

const initialData = Array(30).fill(0).map((_, i) => ({
  time: i,
  active: 0,
  ringing: 0,
  transferred: 0
}));

export default function LiveCampaignMonitor({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const [data, setData] = useState(initialData);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("STARTING");

  const [stats, setStats] = useState({
     total: 0,
     dialed: 0,
     answered: 0,
     transferred: 0,
     voicemail: 0,
     failed: 0,
     conversion_rate: 0
  });

  // ── Real-time call tracking from WebSocket ────────────────────────────
  const { events } = useWebSocket();
  const activeCalls = useRef(0);
  const transferredCalls = useRef(0);

  // Track live call counts from WebSocket events scoped to this campaign
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0]; // most recent event
    if (!latest || latest.campaign_id !== resolvedParams.id) return;

    if (latest.event === "CALL_STARTED") {
      activeCalls.current = Math.max(0, activeCalls.current + 1);
    } else if (latest.event === "CALL_ENDED") {
      activeCalls.current = Math.max(0, activeCalls.current - 1);
      if (latest.cause === "NORMAL_CLEARING") {
        transferredCalls.current += 1;
      }
    }
  }, [events, resolvedParams.id]);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/campaigns/${resolvedParams.id}/metrics`);
      if (res.ok) {
        const d = await res.json();
        setStats({
          total: d.total || 0,
          dialed: d.dialed || 0,
          answered: d.answered || 0,
          transferred: d.transfers || 0,
          voicemail: d.voicemail || 0,
          failed: d.failed || 0,
          conversion_rate: d.conversion_rate || 0
        });
        setStatus(d.status);
        if (d.total > 0) {
          setProgress(Math.floor((d.dialed / d.total) * 100));
        }
      }
    } catch(e) {
      console.error("Metrics fetch failed", e);
    }
  }, [resolvedParams.id]);

  useEffect(() => {
     const interval = setInterval(fetchMetrics, 5000);
     fetchMetrics();
     return () => clearInterval(interval);
  }, [fetchMetrics]);

  // Chart tick — reads actual WebSocket-driven counters instead of Math.random()
  useEffect(() => {
     const chartInterval = setInterval(() => {
         setData(prev => {
             const newArray = [...prev.slice(1)];
             const currentActive = activeCalls.current;
             newArray.push({
                 time: prev[prev.length - 1].time + 1,
                 active: currentActive,
                 ringing: Math.max(0, Math.floor(currentActive * 0.4)),
                 transferred: transferredCalls.current,
             });
             // Reset transferred counter each tick so the chart shows per-interval transfers
             transferredCalls.current = 0;
             return newArray;
         });
     }, 2000);
     return () => clearInterval(chartInterval);
  }, []);

  // ── Campaign Action Handlers ──────────────────────────────────────────────
  const handleAction = async (action: string) => {
    try {
      const method = action === 'delete' ? 'DELETE' : 'POST';
      const url = action === 'delete'
        ? `${API_URL}/campaigns/${resolvedParams.id}`
        : `${API_URL}/campaigns/${resolvedParams.id}/${action}`;
      
      const res = await fetch(url, { method });
      if (res.ok) {
        await fetchMetrics(); // Refresh status immediately
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || `Action ${action} failed`);
      }
    } catch (err) {
      alert(`Failed to execute: ${action}`);
    }
  };

  const total = stats.total > 0 ? stats.total : 1;
  const no_answer = stats.dialed - stats.answered - stats.failed - stats.voicemail;

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-[1400px] mx-auto relative z-10">
      
      {/* Top Banner Control Panel */}
      <div className="flex items-center justify-between mb-8">
        <div>
           <div className="flex items-center gap-3 mb-2">
             <Link href="/campaigns" className="text-muted-foreground hover:text-white transition-colors">
               <ArrowLeft className="w-5 h-5" />
             </Link>
             <h1 className="text-3xl font-semibold tracking-tight text-white dark:text-white">Campaign Execution</h1>
             <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border 
                ${status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 
                  status === 'PAUSED' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                  status === 'COMPLETE' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                  status === 'ABORTED' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                  'bg-neutral-500/10 text-neutral-400 border-neutral-500/20'}`}>
                {status === 'ACTIVE' && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
                {status}
             </span>
           </div>
           <p className="text-muted-foreground font-mono text-sm leading-none opacity-50">PROCESS_ID: {resolvedParams.id}</p>
        </div>

        <div className="flex gap-3">
           {/* Start / Resume button — shown when DRAFT or PAUSED */}
           {(status === 'DRAFT' || status === 'PAUSED') && (
             <button
               onClick={() => handleAction('start')}
               className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 px-5 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2"
             >
                <Play className="w-4 h-4" /> {status === 'PAUSED' ? 'Resume' : 'Start'}
             </button>
           )}
           
           {/* Pause button — only when ACTIVE */}
           {status === 'ACTIVE' && (
             <button
               onClick={() => handleAction('pause')}
               className="bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 px-5 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2"
             >
                <Pause className="w-4 h-4" /> Suspend
             </button>
           )}
           
           {/* Abort button — when ACTIVE or PAUSED */}
           {(status === 'ACTIVE' || status === 'PAUSED') && (
             <button
               onClick={() => {
                 if (confirm('Are you sure you want to force-abort this campaign? Remaining contacts will be cleared.')) {
                   handleAction('stop');
                 }
               }}
               className="bg-destructive/10 text-destructive-foreground border border-destructive/20 hover:bg-destructive/20 px-5 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2"
             >
                <Square className="w-4 h-4" /> Force Abort
             </button>
           )}
           
           {/* Terminal state indicators */}
           {status === 'COMPLETE' && (
             <span className="text-blue-400 bg-blue-500/5 border border-blue-500/20 px-5 py-2.5 rounded-lg font-medium flex items-center gap-2">
               ✓ Campaign Completed
             </span>
           )}
           {status === 'ABORTED' && (
             <span className="text-red-400 bg-red-500/5 border border-red-500/20 px-5 py-2.5 rounded-lg font-medium flex items-center gap-2">
               ✕ Aborted
             </span>
           )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
         
         <div className="lg:col-span-3 space-y-6">
            <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
               <div className="flex items-center justify-between mb-8">
                  <h3 className="text-lg font-medium text-white flex items-center gap-2"><Activity className="w-5 h-5 text-emerald-400" /> Real-Time Call Graph (60s)</h3>
                  <div className="flex gap-5 text-xs font-medium">
                     <span className="flex items-center gap-2 text-muted-foreground"><span className="w-3 h-3 rounded bg-[#10b981]"></span> Active Pipelines</span>
                     <span className="flex items-center gap-2 text-muted-foreground"><span className="w-3 h-3 rounded bg-[#3b82f6]"></span> Ringing</span>
                     <span className="flex items-center gap-2 text-muted-foreground"><span className="w-3 h-3 rounded bg-[#a855f7]"></span> Human Bridged</span>
                  </div>
               </div>
               
               <div className="h-[320px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                     <AreaChart data={data} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                       <defs>
                         <linearGradient id="colorActive" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                           <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                         </linearGradient>
                         <linearGradient id="colorRinging" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                           <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                         </linearGradient>
                         <linearGradient id="colorTransferred" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#a855f7" stopOpacity={0.4}/>
                           <stop offset="95%" stopColor="#a855f7" stopOpacity={0}/>
                         </linearGradient>
                       </defs>
                       <XAxis dataKey="time" hide />
                       <YAxis stroke="#4b5563" fontSize={12} tickLine={false} axisLine={false} />
                       <Tooltip 
                         contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }} 
                         itemStyle={{ color: '#fff' }} 
                       />
                       <Area type="monotone" dataKey="active" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorActive)" />
                       <Area type="monotone" dataKey="ringing" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorRinging)" />
                       <Area type="monotone" dataKey="transferred" stroke="#a855f7" strokeWidth={2} fillOpacity={1} fill="url(#colorTransferred)" />
                     </AreaChart>
                  </ResponsiveContainer>
               </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                 <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-xl p-5 text-center transition-all hover:bg-white/5">
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3">Answered</div>
                    <div className="text-3xl font-semibold text-white mb-1 tracking-tight">{stats.answered.toLocaleString()}</div>
                    <div className="text-sm font-medium text-emerald-400">{stats.answered > 0 ? ((stats.answered / stats.dialed) * 100).toFixed(1) : 0}%</div>
                 </div>
                 <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-xl p-5 text-center transition-all hover:bg-white/5 shadow-[0_0_30px_rgba(168,85,247,0.1)]">
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 text-purple-300">Live Transfer</div>
                    <div className="text-3xl font-semibold text-purple-400 mb-1 tracking-tight">{stats.transferred.toLocaleString()}</div>
                    <div className="text-sm font-medium text-purple-400">{stats.conversion_rate}%</div>
                 </div>
                 <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-xl p-5 text-center transition-all hover:bg-white/5">
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3">Voicemail</div>
                    <div className="text-3xl font-semibold text-white mb-1 tracking-tight">{stats.voicemail.toLocaleString()}</div>
                    <div className="text-sm font-medium text-muted-foreground">{stats.voicemail > 0 ? ((stats.voicemail / stats.dialed) * 100).toFixed(1) : 0}%</div>
                 </div>
                 <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-xl p-5 text-center transition-all hover:bg-white/5">
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3">No Answer</div>
                    <div className="text-3xl font-semibold text-white mb-1 tracking-tight">{Math.max(0, no_answer).toLocaleString()}</div>
                    <div className="text-sm font-medium text-muted-foreground">{no_answer > 0 ? ((no_answer / stats.dialed) * 100).toFixed(1) : 0}%</div>
                 </div>
                 <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-xl p-5 text-center transition-all hover:bg-white/5 border-red-500/10">
                    <div className="text-xs font-semibold text-red-500/50 uppercase tracking-widest mb-3">Failed / Dead</div>
                    <div className="text-3xl font-semibold text-red-400 mb-1 tracking-tight">{stats.failed.toLocaleString()}</div>
                    <div className="text-sm font-medium text-red-400">{stats.failed > 0 ? ((stats.failed / stats.dialed) * 100).toFixed(1) : 0}%</div>
                 </div>
            </div>
         </div>

         <div className="lg:col-span-1 border border-white/10 bg-background/60 backdrop-blur-2xl rounded-2xl p-6 relative overflow-hidden">
             <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ backgroundImage: 'radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0, transparent 50%), radial-gradient(at 100% 100%, hsla(160,60%,45%,0.3) 0, transparent 50%)' }} />
             
             <div className="relative z-10">
                 <h3 className="text-lg font-medium text-white mb-8">Run Logistics</h3>
                 
                 <div className="space-y-4 mb-10">
                     <div className="flex justify-between items-end">
                        <span className="text-5xl font-semibold text-emerald-400 tracking-tighter">{progress}%</span>
                     </div>
                     <div className="w-full bg-white/5 rounded-full h-4 overflow-hidden border border-white/10 p-0.5 shadow-inner">
                        <div className="bg-emerald-500 h-full rounded-full transition-all duration-1000 relative shadow-[0_0_10px_rgba(16,185,129,0.5)]" style={{ width: `${progress}%` }}>
                           <div className="absolute inset-0 bg-white/20 w-full h-full animate-soft-pulse" />
                        </div>
                     </div>
                     <p className="text-xs text-muted-foreground text-center font-mono opacity-60">
                        {stats.dialed.toLocaleString()} / {stats.total.toLocaleString()} Dials Fired
                     </p>
                 </div>
             </div>
         </div>

      </div>
    </div>
  );
}

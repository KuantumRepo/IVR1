'use client';

import { useState, useEffect } from 'react';
import { Loader2, Phone, X, PhoneOff, Settings2, ShieldCheck, UserCircle, PhoneIncoming, Bot, Voicemail, Volume2, Info } from 'lucide-react';

// ── AMD Mode definitions (shared with campaign wizard) ──────────────────
const CAMPAIGN_MODES = [
  {
    id: "A",
    label: "Aggressive",
    icon: PhoneOff,
    color: "emerald",
    description: "Hang up immediately on machine detection.",
    behavior: ["Machine → Hang up", "Human → Play IVR", "Unknown → Hang up"],
    recommended: true,
  },
  {
    id: "B",
    label: "VM Drop",
    icon: Voicemail,
    color: "blue",
    description: "Wait for beep, then play a pre-recorded message.",
    behavior: ["Machine → Wait for beep → Play audio", "Human → Play IVR", "Unknown → Hang up"],
    recommended: false,
  },
  {
    id: "C",
    label: "Conservative",
    icon: ShieldCheck,
    color: "amber",
    description: "When unsure, assume human and play the IVR.",
    behavior: ["Machine → Hang up", "Human → Play IVR", "Unknown → Play IVR"],
    recommended: false,
  },
];

const colorMap: Record<string, { bg: string; border: string; text: string; ring: string; dot: string }> = {
  emerald: {
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    ring: "ring-emerald-500/40",
    dot: "bg-emerald-400",
  },
  blue: {
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    text: "text-blue-400",
    ring: "ring-blue-500/40",
    dot: "bg-blue-400",
  },
  amber: {
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    text: "text-amber-400",
    ring: "ring-amber-500/40",
    dot: "bg-amber-400",
  },
};

export default function TestFlowModal({ isOpen, onClose, scripts }: { isOpen: boolean, onClose: () => void, scripts: any[] }) {
  const [gateways, setGateways] = useState<any[]>([]);
  const [callerIds, setCallerIds] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [audioFiles, setAudioFiles] = useState<any[]>([]);
  
  const [loadingConfig, setLoadingConfig] = useState(false);

  const [scriptId, setScriptId] = useState('');
  const [gatewayId, setGatewayId] = useState('');
  const [callerIdId, setCallerIdId] = useState('');
  const [agentId, setAgentId] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [enableAmd, setEnableAmd] = useState(true);
  const [campaignMode, setCampaignMode] = useState('A');
  const [vmDropAudioId, setVmDropAudioId] = useState('');

  const [callStatus, setCallStatus] = useState<'idle' | 'calling'>('idle');
  const [testCallId, setTestCallId] = useState<string | null>(null);
  
  const [logs, setLogs] = useState<{timestamp: string, tag: string, detail: string}[]>([]);

  useEffect(() => {
    if (isOpen) {
      // Default to first script if not set
      if (!scriptId && scripts.length > 0) {
        setScriptId(scripts[0].id);
      }
      
      setLoadingConfig(true);
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      
      Promise.all([
        fetch(`${API_BASE}/sip-gateways/`).then(r => r.json()).catch(() => []),
        fetch(`${API_BASE}/caller-ids/`).then(r => r.json()).catch(() => []),
        fetch(`${API_BASE}/agents/`).then(r => r.json()).catch(() => []),
        fetch(`${API_BASE}/audio/`).then(r => r.json()).catch(() => []),
      ]).then(([g_data, c_data, a_data, af_data]) => {
        setGateways(Array.isArray(g_data) ? g_data : []);
        setCallerIds(Array.isArray(c_data) ? c_data : []);
        setAgents(Array.isArray(a_data) ? a_data : []);
        setAudioFiles(Array.isArray(af_data) ? af_data : []);
        
        // Auto-select first available options if any
        if (g_data?.length) setGatewayId(g_data[0].id);
        if (c_data?.length) setCallerIdId(c_data[0].id);
        
        setLoadingConfig(false);
      });
    } else {
        setCallStatus('idle');
        setTestCallId(null);
        setLogs([]);
    }
  }, [isOpen, scripts]);
  
  useEffect(() => {
    let ws: WebSocket;
    if (callStatus === 'calling') {
        const HOST = process.env.NEXT_PUBLIC_API_URL ? process.env.NEXT_PUBLIC_API_URL.replace('http', 'ws').replace('/api/v1', '') : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
        ws = new WebSocket(`${HOST}/ws/test-logs`);
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event) {
                    const parsed = JSON.parse(data.event);
                    setLogs(prev => [...prev, parsed]);
                }
            } catch(e) {}
        };
    }
    return () => {
        if(ws) ws.close();
    }
  }, [callStatus]);

  if (!isOpen) return null;

  const handleMakeCall = async () => {
    if (!phoneNumber || !scriptId) return alert("Flow Context and Target Phone number are required.");

    setLogs([]);
    setCallStatus('calling');
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      const res = await fetch(`${API_BASE}/call-scripts/test-call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: phoneNumber,
          script_id: scriptId,
          gateway_id: gatewayId || null,
          caller_id_id: callerIdId || null,
          agent_id: agentId || null,
          enable_amd: enableAmd,
          campaign_mode: enableAmd ? campaignMode : 'A',
          vm_drop_audio_id: (campaignMode === 'B' && vmDropAudioId) ? vmDropAudioId : null,
        })
      });

      if (!res.ok) {
        throw new Error(await res.text());
      }

      const data = await res.json();
      setTestCallId(data.test_call_id);
    } catch (err: any) {
      console.error(err);
      alert(`Simulation Call failed: ${err.message}`);
      setCallStatus('idle');
    }
  };

  const handleHangupOrCancel = async () => {
    if (callStatus === 'calling' && testCallId) {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
        await fetch(`${API_BASE}/call-scripts/test-call/${testCallId}`, { method: 'DELETE' });
      } catch (err) {
        console.error("Failed to hangup test call", err);
      }
    }
    setCallStatus('idle');
    setTestCallId(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#0a0a0f] border border-white/10 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/10 bg-white/5 flex-shrink-0">
          <div className="flex items-center gap-3 text-white">
            <div className="p-2 bg-indigo-500/20 rounded-lg">
              <Phone className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h3 className="font-semibold text-lg">Test Flow Simulator</h3>
              <p className="text-xs text-zinc-400">Launch a live test natively through the backend engine.</p>
            </div>
          </div>
          {callStatus !== 'calling' && (
            <button onClick={onClose} className="p-2 text-zinc-400 hover:text-white transition-colors hover:bg-white/10 rounded-lg">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {loadingConfig ? (
            <div className="py-12 flex flex-col items-center justify-center text-zinc-500 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
              <span className="text-sm">Binding system dependencies...</span>
            </div>
          ) : (
            <>
              {/* Target Setup */}
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5 flex flex-wrap gap-1.5 items-center">
                    <Settings2 className="w-3.5 h-3.5" /> Select Flow Context
                  </label>
                  <select
                    disabled={callStatus === 'calling'}
                    value={scriptId}
                    onChange={(e) => setScriptId(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
                  >
                    <option value="" disabled className="bg-zinc-900">-- Choose IVR Script --</option>
                    {scripts.map(s => (
                      <option key={s.id} value={s.id} className="bg-zinc-900">{s.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">SIP Gateway</label>
                  <select
                    disabled={callStatus === 'calling'}
                    value={gatewayId}
                    onChange={(e) => setGatewayId(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
                  >
                    <option value="" className="bg-zinc-900">System Default</option>
                    {gateways.map(g => (
                      <option key={g.id} value={g.id} className="bg-zinc-900">{g.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Caller ID</label>
                  <select
                    disabled={callStatus === 'calling'}
                    value={callerIdId}
                    onChange={(e) => setCallerIdId(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
                  >
                    <option value="" className="bg-zinc-900">Anonymous</option>
                    {callerIds.map(c => (
                      <option key={c.id} value={c.id} className="bg-zinc-900">
                        {c.name ? `${c.name} (${c.phone_number})` : c.phone_number}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="col-span-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5 flex items-center gap-1.5">
                    <UserCircle className="w-3.5 h-3.5" /> Target Agent (For Transfer Sim)
                  </label>
                  <select
                    disabled={callStatus === 'calling'}
                    value={agentId}
                    onChange={(e) => setAgentId(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
                  >
                    <option value="" className="bg-zinc-900">None (Route to Sales Queue)</option>
                    {agents.map(a => (
                      <option key={a.id} value={a.id} className="bg-zinc-900">{a.name} (ext: {a.sip_extension || a.phone_or_sip})</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* ── AMD Section ───────────────────────────────────────────── */}
              <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                
                {/* AMD Toggle Header */}
                <div className="px-4 py-3 flex items-center justify-between">
                  <label className="flex items-center gap-2.5 cursor-pointer group">
                    <Bot className="w-4 h-4 text-emerald-400" />
                    <div>
                      <p className="text-sm font-medium text-white group-hover:text-indigo-300 transition-colors">Answering Machine Detection</p>
                      <p className="text-[11px] text-zinc-500 mt-0.5">3-Layer AI: heuristic → Whisper → beep detector</p>
                    </div>
                  </label>
                  <button
                    type="button"
                    disabled={callStatus === 'calling'}
                    onClick={() => setEnableAmd(!enableAmd)}
                    className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 disabled:opacity-50 ${enableAmd ? 'bg-emerald-500' : 'bg-white/15'}`}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${enableAmd ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                </div>

                {/* AMD Mode Selector — only visible when AMD is on */}
                {enableAmd && (
                  <div className="px-4 pb-4 pt-1 border-t border-white/5 space-y-3 animate-in fade-in slide-in-from-top-2 duration-200">
                    
                    {/* Mode cards — compact for modal */}
                    <div className="grid grid-cols-3 gap-2 mt-2">
                      {CAMPAIGN_MODES.map((mode) => {
                        const c = colorMap[mode.color];
                        const isSelected = campaignMode === mode.id;
                        const Icon = mode.icon;
                        return (
                          <button
                            key={mode.id}
                            type="button"
                            disabled={callStatus === 'calling'}
                            onClick={() => setCampaignMode(mode.id)}
                            className={`relative text-left p-3 rounded-lg border transition-all duration-200 cursor-pointer disabled:opacity-50
                              ${isSelected 
                                ? `${c.bg} ${c.border} ring-1 ${c.ring}` 
                                : 'bg-black/20 border-white/5 hover:border-white/15'
                              }`}
                          >
                            {mode.recommended && (
                              <span className="absolute -top-1.5 right-2 text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/20">
                                Default
                              </span>
                            )}

                            <div className="flex items-center gap-2 mb-1.5">
                              <div className={`w-6 h-6 rounded-md flex items-center justify-center ${isSelected ? c.bg : 'bg-white/5'} border ${isSelected ? c.border : 'border-white/10'}`}>
                                <Icon className={`w-3 h-3 ${isSelected ? c.text : 'text-muted-foreground'}`} />
                              </div>
                              <div>
                                <div className={`text-xs font-semibold ${isSelected ? 'text-white' : 'text-white/70'}`}>
                                  Mode {mode.id}
                                </div>
                                <div className={`text-[10px] ${isSelected ? c.text : 'text-muted-foreground'}`}>
                                  {mode.label}
                                </div>
                              </div>
                            </div>

                            <p className="text-[10px] text-muted-foreground leading-relaxed">
                              {mode.description}
                            </p>
                          </button>
                        );
                      })}
                    </div>

                    {/* VM Drop Audio Selector — only for Mode B */}
                    {campaignMode === "B" && (
                      <div className="bg-blue-500/5 border border-blue-500/15 rounded-lg p-3 animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex items-start gap-2.5">
                          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Volume2 className="w-4 h-4 text-blue-400" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <label className="text-xs font-medium text-white block mb-1">VM Drop Audio</label>
                            <select
                              disabled={callStatus === 'calling'}
                              value={vmDropAudioId}
                              onChange={(e) => setVmDropAudioId(e.target.value)}
                              className="w-full bg-black/40 border border-blue-500/20 rounded-md px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500/40 disabled:opacity-50"
                            >
                              <option value="">-- Select audio file --</option>
                              {audioFiles.map((af: any) => (
                                <option key={af.id} value={af.id}>
                                  {af.name} {af.duration_ms ? `(${(af.duration_ms / 1000).toFixed(1)}s)` : ''}
                                </option>
                              ))}
                            </select>
                            {!vmDropAudioId && (
                              <div className="flex items-center gap-1 mt-1.5">
                                <Info className="w-3 h-3 text-amber-400" />
                                <span className="text-[10px] text-amber-400/80">No audio — machines will be hung up without a message.</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Action Number */}
              <div className="pt-1">
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5 flex items-center gap-1.5">
                  <PhoneIncoming className="w-3.5 h-3.5 text-zinc-400" /> Dial Target Phone Number
                </label>
                <input
                  disabled={callStatus === 'calling'}
                  type="text"
                  placeholder="+1 (555) 000-0000"
                  value={phoneNumber}
                  onChange={e => setPhoneNumber(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-lg font-medium text-white placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors"
                />
              </div>

              {/* Terminal Logs */}
              {callStatus === 'calling' && (
                <div className="mt-4 border border-white/10 rounded-lg bg-black overflow-hidden animate-in slide-in-from-bottom-2">
                  <div className="bg-white/5 px-4 py-2 border-b border-white/10 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold font-mono">Live Session Trace</span>
                  </div>
                  <div className="p-4 h-48 overflow-y-auto font-mono text-xs space-y-2 flex flex-col-reverse">
                    <div className="flex flex-col gap-1.5">
                        {logs.map((log, i) => (
                        <div key={i} className="flex items-start gap-3">
                            <span className="text-zinc-500 shrink-0">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                            <span className={`shrink-0 ${log.tag === 'SYSTEM' ? 'text-indigo-400' : log.tag === 'NETWORK' ? 'text-cyan-400' : log.tag === 'AMD' ? 'text-amber-400' : log.tag === 'ROUTING' ? 'text-emerald-400' : 'text-zinc-300'}`}>[{log.tag}]</span>
                            <span className="text-zinc-300 break-words">{log.detail}</span>
                        </div>
                        ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-5 border-t border-white/10 bg-black/20 flex gap-3 flex-shrink-0">
          {callStatus === 'calling' ? (
            <>
              <div className="flex-1 px-4 flex items-center justify-center gap-2 border border-indigo-500/30 bg-indigo-500/10 text-indigo-400 rounded-lg text-sm font-medium font-mono animate-pulse">
                <Loader2 className="w-4 h-4 animate-spin" /> In Progress...
              </div>
              <button
                onClick={handleHangupOrCancel}
                className="flex-[0.5] py-2.5 rounded-lg font-medium transition-colors bg-red-500/20 text-red-500 hover:bg-red-500/30 flex items-center justify-center gap-2 text-sm"
              >
                <PhoneOff className="w-4 h-4" /> Cancel / Hang Up
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleHangupOrCancel}
                className="flex-1 py-2.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 transition-colors text-sm font-medium"
              >
                Cancel
              </button>
              <button
                disabled={loadingConfig || !phoneNumber}
                onClick={handleMakeCall}
                className="flex-[1.5] py-2.5 rounded-lg font-medium transition-colors bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 shadow-[0_0_15px_rgba(99,102,241,0.3)] flex items-center justify-center gap-2 text-sm"
              >
                <Phone className="w-4 h-4 fill-current" /> Initialize Test Call
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

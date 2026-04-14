"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowLeft, CheckCircle2, PlayCircle, Loader2, Bot, PhoneOff, Voicemail, ShieldCheck, Volume2, Info } from "lucide-react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

// ── Campaign Mode definitions ──────────────────────────────────────────────
const CAMPAIGN_MODES = [
  {
    id: "A",
    label: "Aggressive",
    icon: PhoneOff,
    color: "emerald",
    description: "Immediately hang up when a voicemail or machine is detected. Maximizes SIP minute savings.",
    behavior: ["Machine → Hang up instantly", "Human → Play IVR script", "Unknown → Hang up (safe default)"],
    recommended: true,
    tagline: "Best for high-volume campaigns where every second of SIP billing counts."
  },
  {
    id: "B",
    label: "VM Drop",
    icon: Voicemail,
    color: "blue",
    description: "Wait for the voicemail beep, then play a pre-recorded message before hanging up.",
    behavior: ["Machine → Wait for beep → Play audio → Hang up", "Human → Play IVR script", "Unknown → Hang up"],
    recommended: false,
    tagline: "Best when you want to leave a message on every answering machine."
  },
  {
    id: "C",
    label: "Conservative",
    icon: ShieldCheck,
    color: "amber",
    description: "When unsure, assume it's a human and play the IVR. Minimizes missed real humans.",
    behavior: ["Machine → Hang up", "Human → Play IVR script", "Unknown → Treat as human, play IVR"],
    recommended: false,
    tagline: "Best for small lists where reaching every real person matters most."
  },
];

const colorMap: Record<string, { bg: string; border: string; text: string; ring: string; dot: string; glow: string }> = {
  emerald: {
    bg: "bg-emerald-500/5",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    ring: "ring-emerald-500/40",
    dot: "bg-emerald-400",
    glow: "shadow-[0_0_30px_rgba(16,185,129,0.15)]"
  },
  blue: {
    bg: "bg-blue-500/5",
    border: "border-blue-500/30",
    text: "text-blue-400",
    ring: "ring-blue-500/40",
    dot: "bg-blue-400",
    glow: "shadow-[0_0_30px_rgba(59,130,246,0.15)]"
  },
  amber: {
    bg: "bg-amber-500/5",
    border: "border-amber-500/30",
    text: "text-amber-400",
    ring: "ring-amber-500/40",
    dot: "bg-amber-400",
    glow: "shadow-[0_0_30px_rgba(245,158,11,0.15)]"
  },
};

export default function NewCampaignWizard() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const totalSteps = 3;
  const [isSubmitting, setIsSubmitting] = useState(false);

  // External data pools mapping
  const [scripts, setScripts] = useState<any[]>([]);
  const [lists, setLists] = useState<any[]>([]);
  const [gateways, setGateways] = useState<any[]>([]);
  const [callerIds, setCallerIds] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [audioFiles, setAudioFiles] = useState<any[]>([]);

  useEffect(() => {
    // Parallel fetching of all system dependencies
    Promise.all([
      fetch(API_URL + '/call-scripts/').then(r => r.json()).catch(()=>[]),
      fetch(API_URL + '/contact-lists/').then(r => r.json()).catch(()=>[]),
      fetch(API_URL + '/sip-gateways/').then(r => r.json()).catch(()=>[]),
      fetch(API_URL + '/caller-ids/').then(r => r.json()).catch(()=>[]),
      fetch(API_URL + '/agents/').then(r => r.json()).catch(()=>[]),
      fetch(API_URL + '/audio/').then(r => r.json()).catch(()=>[]),
    ]).then(([s_data, l_data, g_data, c_data, a_data, af_data]) => {
      setScripts(s_data);
      setLists(l_data);
      setGateways(g_data);
      setCallerIds(c_data);
      setAgents(a_data);
      setAudioFiles(af_data);
    });
  }, []);

  const [formData, setFormData] = useState({
    name: "",
    description: "",
    script_id: "",
    list_ids: [] as string[],
    gateway_ids: [] as string[],
    caller_ids: [] as string[],
    agent_ids: [] as string[],
    max_concurrent_calls: 10,
    calls_per_second: 1.0,
    enable_amd: true,
    campaign_mode: "A",
    vm_drop_audio_id: "" as string,
    
    ring_timeout: 45,
    gateway_connect_timeout: 30,
    dial_timeout: 60,
    vocal_pause: 2.0,
    idle_looping_delay: 5,
    max_idle_loops: 3
  });

  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleNext = () => setStep(prev => Math.min(prev + 1, totalSteps));
  const handlePrev = () => setStep(prev => Math.max(prev - 1, 1));

  const handleSave = async (startImmediately: boolean) => {
    try {
       setIsSubmitting(true);
       const payload: any = {
           name: formData.name || "Untitled Campaign",
           description: formData.description,
           script_id: formData.script_id,
           list_ids: formData.list_ids,
           gateway_ids: formData.gateway_ids,
           caller_id_ids: formData.caller_ids,
           agent_ids: formData.agent_ids,
           max_concurrent_calls: formData.max_concurrent_calls,
           calls_per_second: formData.calls_per_second,
           enable_amd: formData.enable_amd,
           campaign_mode: formData.enable_amd ? formData.campaign_mode : "A",
           ring_timeout_sec: formData.ring_timeout,
       };
       
       // Only include VM drop audio ID for Mode B
       if (formData.campaign_mode === "B" && formData.vm_drop_audio_id) {
           payload.vm_drop_audio_id = formData.vm_drop_audio_id;
       }
       
       const res = await fetch(API_URL + '/campaigns/', {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify(payload)
       });
       if (!res.ok) throw new Error("Failed to create campaign");
       
       router.push('/campaigns');
    } catch (err) {
       console.error("Save failed", err);
       alert("Failed to initialize engine");
    } finally {
       setIsSubmitting(false);
    }
  }

  const selectedMode = CAMPAIGN_MODES.find(m => m.id === formData.campaign_mode)!;

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-4xl mx-auto relative z-10">
      
      {/* Wizard Header */}
      <div className="mb-12">
        <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Initialize Engine</h1>
        <p className="text-muted-foreground mb-8">Deploy a new highly-concurrent outbound dialing loop.</p>
        
        {/* Progress Bar */}
        <div className="flex items-center gap-2">
           {[1,2,3].map((s) => (
             <div key={s} className="flex-1">
               <div className={`h-1.5 rounded-full transition-all duration-300 ${s <= step ? 'bg-white' : 'bg-white/10'}`} />
               <div className="mt-2 flex items-center justify-between text-xs font-medium">
                 <span className={s <= step ? 'text-white' : 'text-muted-foreground'}>
                    {s === 1 ? 'Basic Info' : s === 2 ? 'Resources' : 'Engine Tuning'}
                 </span>
               </div>
             </div>
           ))}
        </div>
      </div>

      {/* Step Container */}
      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 mb-8 relative overflow-hidden">
         {step === 1 && (
            <div className="space-y-6 animate-in slide-in-from-right-4 fade-in">
              <div>
                <label className="text-sm font-medium text-white mb-2 block">Campaign Name</label>
                <input 
                  type="text" 
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 transition-colors"
                  placeholder="e.g. Solar Panel Outreach Q2"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-white mb-2 block">Internal Description</label>
                <textarea 
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 transition-colors h-32 resize-none"
                  placeholder="Optional context regarding this dial loop..."
                />
              </div>
            </div>
         )}

         {step === 2 && (
            <div className="space-y-6 animate-in slide-in-from-right-4 fade-in">
              <div>
                <label className="text-sm font-medium text-white mb-2 block">Interactive Script Protocol</label>
                <select 
                  value={formData.script_id}
                  onChange={(e) => setFormData({...formData, script_id: e.target.value})}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                   <option value="">-- Select Call Script --</option>
                   {scripts.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <p className="text-xs text-muted-foreground mt-2">The Kokoro TTS execution sequence played upon human answer.</p>
              </div>

              <div>
                <label className="text-sm font-medium text-white mb-2 block">Target Audience (CSV List)</label>
                <select 
                  value={formData.list_ids[0] || ""}
                  onChange={(e) => setFormData({...formData, list_ids: [e.target.value]})}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                   <option value="">-- Attach Contact List --</option>
                   {lists.map(l => <option key={l.id} value={l.id}>{l.name} ({l.total_contacts} leads)</option>)}
                </select>
              </div>

              {/* Transmission Trunk — single select */}
              <div>
                <label className="text-sm font-medium text-white mb-2 block">Transmission Trunk (SIP Gateway)</label>
                <select 
                  value={formData.gateway_ids[0] || ""}
                  onChange={(e) => setFormData({...formData, gateway_ids: [e.target.value]})}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 appearance-none">
                   <option value="">-- Select SIP Gateway --</option>
                   {gateways.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
              
              {/* ── Caller ID Pool ─────────────────────────────────────────── */}
              <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <label className="text-sm font-medium text-white block">Caller ID Pool (Rotation)</label>
                    <p className="text-xs text-muted-foreground mt-1">Select numbers to rotate through. The dialer cycles through them to avoid spam flags.</p>
                  </div>
                  {formData.caller_ids.length > 0 && (
                    <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
                      {formData.caller_ids.length} selected
                    </span>
                  )}
                </div>
                
                {callerIds.length === 0 ? (
                  <div className="text-center py-6 text-muted-foreground text-sm">
                    No caller IDs configured. <a href="/caller-ids" className="text-emerald-400 hover:underline">Add some first →</a>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-1">
                    {callerIds.map((c: any) => {
                      const isSelected = formData.caller_ids.includes(c.id);
                      return (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => {
                            setFormData(prev => ({
                              ...prev,
                              caller_ids: isSelected 
                                ? prev.caller_ids.filter(id => id !== c.id) 
                                : [...prev.caller_ids, c.id]
                            }));
                          }}
                          className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all duration-150 ${
                            isSelected 
                              ? 'bg-emerald-500/10 border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.1)]' 
                              : 'bg-black/20 border-white/5 hover:border-white/15 hover:bg-white/[0.03]'
                          }`}
                        >
                          <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                            isSelected ? 'border-emerald-400 bg-emerald-500' : 'border-white/20'
                          }`}>
                            {isSelected && (
                              <svg className="w-3 h-3 text-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${isSelected ? 'text-white' : 'text-white/70'}`}>{c.name || 'Unnamed'}</div>
                            <div className={`text-xs font-mono ${isSelected ? 'text-emerald-400/80' : 'text-muted-foreground'}`}>{c.phone_number}</div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ── Live Agent Pool ────────────────────────────────────────── */}
              <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <label className="text-sm font-medium text-white block">Live Agent Pool (Transfer Targets)</label>
                    <p className="text-xs text-muted-foreground mt-1">Select agents available for live call transfers. Calls are routed to available agents in round-robin.</p>
                  </div>
                  {formData.agent_ids.length > 0 && (
                    <span className="text-xs font-bold text-purple-400 bg-purple-500/10 px-3 py-1 rounded-full border border-purple-500/20">
                      {formData.agent_ids.length} selected
                    </span>
                  )}
                </div>
                
                {agents.length === 0 ? (
                  <div className="text-center py-6 text-muted-foreground text-sm">
                    No agents configured. <a href="/agents" className="text-purple-400 hover:underline">Add agents first →</a>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-1">
                    {agents.map((a: any) => {
                      const isSelected = formData.agent_ids.includes(a.id);
                      return (
                        <button
                          key={a.id}
                          type="button"
                          onClick={() => {
                            setFormData(prev => ({
                              ...prev,
                              agent_ids: isSelected 
                                ? prev.agent_ids.filter(id => id !== a.id) 
                                : [...prev.agent_ids, a.id]
                            }));
                          }}
                          className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all duration-150 ${
                            isSelected 
                              ? 'bg-purple-500/10 border-purple-500/30 shadow-[0_0_15px_rgba(168,85,247,0.1)]' 
                              : 'bg-black/20 border-white/5 hover:border-white/15 hover:bg-white/[0.03]'
                          }`}
                        >
                          <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                            isSelected ? 'border-purple-400 bg-purple-500' : 'border-white/20'
                          }`}>
                            {isSelected && (
                              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${isSelected ? 'text-white' : 'text-white/70'}`}>{a.name}</div>
                            <div className={`text-xs font-mono ${isSelected ? 'text-purple-400/80' : 'text-muted-foreground'}`}>
                              ext: {a.sip_extension || a.phone_or_sip}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
         )}

         {step === 3 && (
            <div className="space-y-8 animate-in slide-in-from-right-4 fade-in">

              {/* ── Dialer Tuning ─────────────────────────────────────────── */}
              <div className="grid grid-cols-2 gap-8">
                <div>
                  <label className="text-sm font-medium text-white mb-4 block">Calls Per Second (CPS)</label>
                  <div className="flex items-center gap-4">
                    <input 
                      type="range" min="0.5" max="10" step="0.5"
                      value={formData.calls_per_second}
                      onChange={(e) => setFormData({...formData, calls_per_second: parseFloat(e.target.value)})}
                      className="flex-1 accent-emerald-500"
                    />
                    <span className="text-xl font-medium w-12 text-right">{formData.calls_per_second.toFixed(1)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">Strict token-bucket rate limits applied to FreeSWITCH bgapi origination.</p>
                </div>
                
                <div>
                  <label className="text-sm font-medium text-white mb-4 block">Max Concurrent Connections</label>
                  <div className="flex items-center gap-4">
                    <input 
                      type="range" min="1" max="100" step="1"
                      value={formData.max_concurrent_calls}
                      onChange={(e) => setFormData({...formData, max_concurrent_calls: parseInt(e.target.value)})}
                      className="flex-1 accent-emerald-500"
                    />
                    <span className="text-xl font-medium w-12 text-right">{formData.max_concurrent_calls}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">Total simultaneous active calls allowed network-wide.</p>
                </div>
              </div>

              {/* ── AMD Section ───────────────────────────────────────────── */}
              <div className="border-t border-white/5 pt-6">
                
                {/* AMD Master Toggle */}
                <div className="flex items-center justify-between mb-6">
                  <label className="flex items-center gap-3 cursor-pointer group">
                    <div className={`w-12 h-6 rounded-full transition-colors relative ${formData.enable_amd ? 'bg-emerald-500' : 'bg-white/10'}`} onClick={() => setFormData({...formData, enable_amd: !formData.enable_amd})}>
                       <div className={`absolute top-1 transform transition-transform bg-white w-4 h-4 rounded-full ${formData.enable_amd ? 'translate-x-7' : 'translate-x-1'}`} />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white group-hover:text-emerald-400 transition-colors flex items-center gap-2">
                        <Bot className="w-4 h-4" />
                        Answering Machine Detection
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">3-Layer AI detection: heuristic → Whisper AI → beep detector</div>
                    </div>
                  </label>
                </div>

                {/* AMD Mode Selector — only visible when AMD is on */}
                {formData.enable_amd && (
                  <div className="space-y-5 animate-in fade-in slide-in-from-top-2 duration-300">
                    
                    {/* Mode Cards */}
                    <div className="grid grid-cols-3 gap-3">
                      {CAMPAIGN_MODES.map((mode) => {
                        const c = colorMap[mode.color];
                        const isSelected = formData.campaign_mode === mode.id;
                        const Icon = mode.icon;
                        return (
                          <button
                            key={mode.id}
                            type="button"
                            onClick={() => setFormData({...formData, campaign_mode: mode.id})}
                            className={`relative text-left p-4 rounded-xl border transition-all duration-200 cursor-pointer
                              ${isSelected 
                                ? `${c.bg} ${c.border} ${c.glow} ring-1 ${c.ring}` 
                                : 'bg-black/20 border-white/5 hover:border-white/15 hover:bg-white/[0.02]'
                              }`}
                          >
                            {/* Recommended badge */}
                            {mode.recommended && (
                              <span className="absolute -top-2 right-3 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/20">
                                Recommended
                              </span>
                            )}

                            <div className="flex items-center gap-2.5 mb-2.5">
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isSelected ? c.bg : 'bg-white/5'} border ${isSelected ? c.border : 'border-white/10'}`}>
                                <Icon className={`w-4 h-4 ${isSelected ? c.text : 'text-muted-foreground'}`} />
                              </div>
                              <div>
                                <div className={`text-sm font-semibold ${isSelected ? 'text-white' : 'text-white/70'}`}>
                                  Mode {mode.id}
                                </div>
                                <div className={`text-xs ${isSelected ? c.text : 'text-muted-foreground'}`}>
                                  {mode.label}
                                </div>
                              </div>
                            </div>

                            <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                              {mode.description}
                            </p>

                            {/* Behavior list */}
                            <div className="space-y-1.5">
                              {mode.behavior.map((b, i) => (
                                <div key={i} className="flex items-start gap-1.5">
                                  <span className={`w-1 h-1 rounded-full mt-1.5 flex-shrink-0 ${isSelected ? c.dot : 'bg-white/20'}`} />
                                  <span className="text-[11px] text-muted-foreground leading-snug">{b}</span>
                                </div>
                              ))}
                            </div>
                          </button>
                        );
                      })}
                    </div>

                    {/* VM Drop Audio Selector — only for Mode B */}
                    {formData.campaign_mode === "B" && (
                      <div className="bg-blue-500/5 border border-blue-500/15 rounded-xl p-5 animate-in fade-in slide-in-from-top-2 duration-300">
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Volume2 className="w-5 h-5 text-blue-400" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <label className="text-sm font-medium text-white block mb-1">Voicemail Drop Audio</label>
                            <p className="text-xs text-muted-foreground mb-3">
                              This audio will play automatically after the voicemail beep is detected. Upload audio files in the <a href="/audio" className="text-blue-400 hover:text-blue-300 underline underline-offset-2">Audio Library</a>.
                            </p>
                            <select
                              value={formData.vm_drop_audio_id}
                              onChange={(e) => setFormData({...formData, vm_drop_audio_id: e.target.value})}
                              className="w-full bg-black/40 border border-blue-500/20 rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/40 appearance-none"
                            >
                              <option value="">-- Select audio file --</option>
                              {audioFiles.map((af: any) => (
                                <option key={af.id} value={af.id}>
                                  {af.name} {af.duration_ms ? `(${(af.duration_ms / 1000).toFixed(1)}s)` : ''}
                                </option>
                              ))}
                            </select>
                            {!formData.vm_drop_audio_id && (
                              <div className="flex items-center gap-1.5 mt-2">
                                <Info className="w-3 h-3 text-amber-400" />
                                <span className="text-[11px] text-amber-400/80">No audio selected — machines will be hung up without a message.</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Selected mode summary */}
                    <div className="flex items-center gap-2 px-1">
                      <Info className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                      <p className="text-xs text-muted-foreground italic">{selectedMode.tagline}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Advanced Configurations ───────────────────────────────── */}
              <div className="border-t border-white/5 mt-6 pt-4">
                 <button 
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="text-sm text-emerald-400 font-medium hover:text-emerald-300 transition-colors flex items-center gap-2"
                 >
                    {showAdvanced ? "- Hide" : "+ Show"} Advanced Engine Timing Configurations
                 </button>

                 {showAdvanced && (
                    <div className="mt-6 grid grid-cols-2 gap-6 bg-black/20 p-6 rounded-xl border border-white/5 animate-in fade-in slide-in-from-top-2">
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Ring timeout (seconds)</label>
                         <input type="number" value={formData.ring_timeout} onChange={e => setFormData({...formData, ring_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Gateway connect timeout (s)</label>
                         <input type="number" value={formData.gateway_connect_timeout} onChange={e => setFormData({...formData, gateway_connect_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Dial timeout (seconds)</label>
                         <input type="number" value={formData.dial_timeout} onChange={e => setFormData({...formData, dial_timeout: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Vocal pause between plays (s)</label>
                         <input type="number" step="0.5" value={formData.vocal_pause} onChange={e => setFormData({...formData, vocal_pause: parseFloat(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Idle looping delay (seconds)</label>
                         <input type="number" value={formData.idle_looping_delay} onChange={e => setFormData({...formData, idle_looping_delay: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                       <div>
                         <label className="text-xs text-muted-foreground uppercase tracking-widest block mb-2">Maximum idle loops</label>
                         <input type="number" value={formData.max_idle_loops} onChange={e => setFormData({...formData, max_idle_loops: parseInt(e.target.value)})} className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
                       </div>
                    </div>
                 )}
              </div>
            </div>
         )}
      </div>

      {/* Navigation Footer */}
      <div className="flex justify-between items-center">
         <button 
           onClick={handlePrev}
           disabled={step === 1}
           className={`px-5 py-2.5 flex items-center gap-2 rounded-lg font-medium transition-colors ${step === 1 ? 'opacity-0 pointer-events-none' : 'text-white hover:bg-white/10'}`}
         >
           <ArrowLeft className="w-4 h-4" /> Back
         </button>

         {step < totalSteps && (
            <button 
              onClick={handleNext}
              className="bg-white text-black hover:bg-neutral-200 px-6 py-2.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]"
            >
              Continue <ArrowRight className="w-4 h-4" />
            </button>
         )}

         {step === totalSteps && (
            <div className="flex gap-3">
              <button 
                onClick={() => handleSave(false)}
                disabled={isSubmitting || !formData.script_id || formData.list_ids.length === 0}
                className="px-6 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2 border border-white/10 text-white hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                 <CheckCircle2 className="w-4 h-4" /> Create Draft
              </button>
              <button 
                onClick={() => handleSave(true)}
                disabled={isSubmitting || !formData.script_id || formData.list_ids.length === 0}
                className="bg-emerald-500 text-black shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:bg-emerald-400 px-6 py-2.5 rounded-lg font-semibold transition-transform active:scale-95 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                 {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                 Launch Engine
              </button>
            </div>
         )}
      </div>

    </div>
  );
}

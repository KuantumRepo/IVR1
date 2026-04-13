"use client";

import { UserPlus, Headset, CircleOff, Copy, Check, RefreshCw, KeyRound, Phone, Wifi, WifiOff } from "lucide-react";
import { useState, useEffect, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

interface AgentData {
  id: string;
  name: string;
  sip_extension: string | null;
  phone_or_sip: string;
  concurrent_cap: number;
  status: string;
  current_calls: number;
  sip_registered: boolean;
  sip_user_agent: string | null;
  created_at: string;
  updated_at: string;
}

interface Credentials {
  sip_extension: string;
  sip_password: string;
  sip_server: string;
  sip_port: number;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [credentialsModal, setCredentialsModal] = useState<Credentials | null>(null);
  const [formData, setFormData] = useState({ name: "", extension: "" });
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API}/agents`);
      if (res.ok) setAgents(await res.json());
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
    // Poll every 10s for live registration updates
    const interval = setInterval(fetchAgents, 10000);
    return () => clearInterval(interval);
  }, [fetchAgents]);

  const handleAddAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.extension) {
      alert("Both Name and Extension are required.");
      return;
    }

    try {
      const res = await fetch(`${API}/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          sip_extension: formData.extension,
          concurrent_cap: 1,
        })
      });
      if (res.ok) {
        const data = await res.json();
        setIsModalOpen(false);
        setFormData({ name: "", extension: "" });
        setCredentialsModal(data.credentials);
        fetchAgents();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to add agent.");
      }
    } catch (e) {
      alert("Failed to add agent.");
    }
  };

  const handleTestAgent = async (agentId: string) => {
    try {
      const res = await fetch(`${API}/agents/${agentId}/test`, { method: 'POST' });
      if (res.ok) alert("Ringing agent softphone!");
      else alert("Engine failed to reach extension.");
    } catch(e) {
      alert("Engine failed to reach extension.");
    }
  };

  const handleDeleteAgent = async (agentId: string) => {
    if (!confirm("Are you sure you want to terminate this agent?")) return;
    try {
      const res = await fetch(`${API}/agents/${agentId}`, { method: 'DELETE' });
      if (res.ok) fetchAgents();
    } catch(e) {
      alert("Failed to delete agent.");
    }
  };

  const handleResetPassword = async (agentId: string) => {
    if (!confirm("Generate a new SIP password for this agent? Their current connection will stop working.")) return;
    try {
      const res = await fetch(`${API}/agents/${agentId}/reset-password`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setCredentialsModal(data.credentials);
      } else {
        alert("Failed to reset password.");
      }
    } catch(e) {
      alert("Failed to reset password.");
    }
  };

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Live Agents</h1>
          <p className="text-muted-foreground">Manage your SIP agent pool for live transfers.</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={fetchAgents} className="p-2.5 rounded-lg border border-white/10 hover:bg-white/5 transition-colors text-muted-foreground hover:text-white" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => setIsModalOpen(true)} className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
            <UserPlus className="w-4 h-4" />
            Add Agent
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.length === 0 ? (
          <div className="col-span-full p-12 text-center bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl">
            <Headset className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
            <h3 className="text-xl font-medium text-white mb-2 tracking-tight">No Agents Configured</h3>
            <p className="text-muted-foreground max-w-md mx-auto">Create your first agent to enable live call bridging via FreeSWITCH.</p>
          </div>
        ) : (
          agents.map((agent) => (
            <div key={agent.id} className="bg-background/60 backdrop-blur-xl border border-white/10 p-6 rounded-2xl group hover:border-white/20 transition-colors flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start mb-4">
                  <div className="w-12 h-12 bg-white/5 rounded-full flex items-center justify-center">
                    <span className="text-lg font-medium text-white">{agent.name.charAt(0)}</span>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    {/* SIP Registration Status */}
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border
                      ${agent.sip_registered
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                      {agent.sip_registered
                        ? <Wifi className="w-3 h-3" />
                        : <WifiOff className="w-3 h-3" />}
                      {agent.sip_registered ? 'Registered' : 'Offline'}
                    </span>
                    {/* Agent Status */}
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border
                      ${agent.status === 'AVAILABLE' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 
                        agent.status === 'ON_CALL' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 
                        'bg-neutral-500/10 text-neutral-400 border-neutral-500/20'}`}>
                      {agent.status === 'AVAILABLE' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                      {agent.status === 'ON_CALL' && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />}
                      {agent.status}
                    </span>
                  </div>
                </div>
                <h3 className="text-lg font-medium text-white">{agent.name}</h3>
                <p className="text-sm text-muted-foreground font-mono mt-1">ext: {agent.sip_extension || agent.phone_or_sip}</p>
                {agent.sip_user_agent && (
                  <p className="text-xs text-muted-foreground/60 mt-1">📱 {agent.sip_user_agent}</p>
                )}
              </div>
              
              <div className="mt-6 flex justify-between items-center border-t border-white/5 pt-4">
                <div className="flex gap-3">
                  <button onClick={() => handleTestAgent(agent.id)} className="text-xs font-medium text-emerald-400/80 hover:text-emerald-400 transition-colors flex items-center gap-1" title="Ring agent">
                    <Phone className="w-3 h-3" /> Test
                  </button>
                  <button onClick={() => handleResetPassword(agent.id)} className="text-xs font-medium text-blue-400/80 hover:text-blue-400 transition-colors flex items-center gap-1" title="Reset SIP password">
                    <KeyRound className="w-3 h-3" /> Reset PW
                  </button>
                </div>
                <button onClick={() => handleDeleteAgent(agent.id)} className="text-xs font-medium text-destructive-foreground hover:text-red-400 transition-colors">Terminate</button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Add Agent Modal ── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-sm shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center p-6 border-b border-white/5">
              <h2 className="text-xl font-semibold text-white">Add Live Agent</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-muted-foreground hover:text-white transition-colors">
                 <CircleOff className="w-5 h-5" />
              </button>
            </div>
            
            <form onSubmit={handleAddAgent} className="p-6 space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Agent Name</label>
                <input type="text" placeholder="e.g. John Doe" value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">SIP Extension</label>
                <input type="text" placeholder="e.g. 1001" value={formData.extension} onChange={(e) => setFormData({...formData, extension: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
                <p className="text-xs text-muted-foreground/60 mt-1">Unique extension number for this agent&apos;s softphone</p>
              </div>
              
              <div className="pt-4 flex justify-end gap-3">
                 <button type="button" onClick={() => setIsModalOpen(false)} className="px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-white/5 transition-colors text-white">Cancel</button>
                 <button type="submit" className="bg-emerald-500 hover:bg-emerald-400 text-black px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors shadow-[0_0_15px_rgba(16,185,129,0.2)]">Provision</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Credentials Modal (shown after creation or password reset) ── */}
      {credentialsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center p-6 border-b border-white/5">
              <h2 className="text-xl font-semibold text-white">SIP Credentials</h2>
              <button onClick={() => setCredentialsModal(null)} className="text-muted-foreground hover:text-white transition-colors">
                <CircleOff className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                <p className="text-amber-400 text-xs font-medium">⚠️ Save these credentials now — the password won&apos;t be shown again.</p>
              </div>

              {[
                { label: "Extension", value: credentialsModal.sip_extension, key: "ext" },
                { label: "Password", value: credentialsModal.sip_password, key: "pw" },
                { label: "SIP Server", value: credentialsModal.sip_server, key: "srv" },
                { label: "Port", value: String(credentialsModal.sip_port), key: "port" },
              ].map(({ label, value, key }) => (
                <div key={key} className="flex items-center justify-between bg-black/30 border border-white/5 rounded-xl px-4 py-3">
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
                    <p className="text-white font-mono text-sm mt-0.5">{value}</p>
                  </div>
                  <button onClick={() => copyToClipboard(value, key)} className="p-2 rounded-lg hover:bg-white/5 transition-colors text-muted-foreground hover:text-white">
                    {copiedField === key ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
              ))}
              
              <div className="pt-2 flex justify-end">
                <button onClick={() => setCredentialsModal(null)} className="bg-white text-black px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors hover:bg-neutral-200">Done</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

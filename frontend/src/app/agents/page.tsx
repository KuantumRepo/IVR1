"use client";

import { UserPlus, Headset, CircleOff, Copy, Check, RefreshCw, KeyRound, Phone, Wifi, WifiOff, Trash2 } from "lucide-react";
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
  callcenter_status: string | null;
  callcenter_state: string | null;
  created_at: string;
  updated_at: string;
}

interface Credentials {
  sip_extension: string;
  sip_password: string;
  sip_server: string;
  sip_port: number;
}

function StatusBadge({ registered, ccStatus, ccState }: { registered: boolean; ccStatus: string | null; ccState: string | null }) {
  // Priority: show callcenter state if available, else SIP registration
  if (ccStatus === "Available" && ccState === "In a queue call") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        On Call
      </span>
    );
  }
  if (ccStatus === "Available") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
        Available
      </span>
    );
  }
  if (registered) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
        <Wifi className="w-3 h-3" />
        Registered
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-neutral-500/10 text-neutral-400 border border-neutral-500/20">
      <WifiOff className="w-3 h-3" />
      Offline
    </span>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [credentialsModal, setCredentialsModal] = useState<Credentials | null>(null);
  const [formData, setFormData] = useState({ name: "", extension: "" });
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API}/agents/`);
      if (res.ok) setAgents(await res.json());
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
    // Poll every 5s for live status updates
    const interval = setInterval(fetchAgents, 5000);
    return () => clearInterval(interval);
  }, [fetchAgents]);

  const handleAddAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.extension) {
      alert("Both Name and Extension are required.");
      return;
    }

    try {
      const res = await fetch(`${API}/agents/`, {
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

  // Summary counts
  const onlineCount = agents.filter(a => a.sip_registered || a.callcenter_status === "Available").length;
  const availableCount = agents.filter(a => a.callcenter_status === "Available").length;

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Live Agents</h1>
          <p className="text-muted-foreground">
            {agents.length} provisioned · <span className="text-emerald-400">{availableCount} available</span> · <span className="text-blue-400">{onlineCount} connected</span>
          </p>
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

      {agents.length === 0 ? (
        <div className="p-12 text-center bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl">
          <Headset className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
          <h3 className="text-xl font-medium text-white mb-2 tracking-tight">No Agents Configured</h3>
          <p className="text-muted-foreground max-w-md mx-auto">Create your first agent to enable live call bridging via FreeSWITCH.</p>
        </div>
      ) : (
        <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/5">
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Agent</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Extension</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Status</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Queue Activity</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Device</th>
                <th className="text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider px-6 py-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent, i) => (
                <tr key={agent.id} className={`border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors ${i % 2 === 0 ? '' : 'bg-white/[0.01]'}`}>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-white/5 rounded-full flex items-center justify-center flex-shrink-0">
                        <span className="text-sm font-medium text-white">{agent.name.charAt(0)}</span>
                      </div>
                      <span className="text-sm font-medium text-white">{agent.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm font-mono text-muted-foreground">{agent.sip_extension || agent.phone_or_sip}</span>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge 
                      registered={agent.sip_registered} 
                      ccStatus={agent.callcenter_status}
                      ccState={agent.callcenter_state}
                    />
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-xs text-muted-foreground">
                      {agent.callcenter_state || '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-xs text-muted-foreground/60 truncate max-w-[150px] block">
                      {agent.sip_user_agent || '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button onClick={() => handleTestAgent(agent.id)} className="p-2 rounded-lg hover:bg-emerald-500/10 text-muted-foreground hover:text-emerald-400 transition-colors" title="Ring agent">
                        <Phone className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => handleResetPassword(agent.id)} className="p-2 rounded-lg hover:bg-blue-500/10 text-muted-foreground hover:text-blue-400 transition-colors" title="Reset SIP password">
                        <KeyRound className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => handleDeleteAgent(agent.id)} className="p-2 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors" title="Terminate agent">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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

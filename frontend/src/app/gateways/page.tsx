"use client";

import { PhoneCall, Plus, Zap, X } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import TestTrunkModal from "./TestTrunkModal";

export default function GatewaysPage() {
  const [gateways, setGateways] = useState<any[]>([]);
  const [gwStatuses, setGwStatuses] = useState<Record<string, any>>({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: "", host: "", username: "", sip_password: "", auth_type: "PASSWORD" as "PASSWORD" | "IP_BASED"
  });

  const fetchGateways = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/sip-gateways/`);
      if (res.ok) setGateways(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  const fetchGatewayStatuses = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/sip-gateways/status`);
      if (res.ok) {
        const data = await res.json();
        const map: Record<string, any> = {};
        data.forEach((s: any) => { map[s.id] = s; });
        setGwStatuses(map);
      }
    } catch (err) { /* silent */ }
  };

  useEffect(() => {
    fetchGateways();
    fetchGatewayStatuses();
    const interval = setInterval(fetchGatewayStatuses, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleAddGateway = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.host || (formData.auth_type === "PASSWORD" && (!formData.username || !formData.sip_password))) {
      alert("All fields are required.");
      return;
    }
    
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/sip-gateways/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          name: formData.name, 
          sip_server: formData.host, 
          auth_type: formData.auth_type,
          ...(formData.auth_type === "PASSWORD" && {
            sip_username: formData.username, 
            sip_password: formData.sip_password
          })
        })
      });
      if (res.ok) {
        setIsModalOpen(false);
        setFormData({ name: "", host: "", username: "", sip_password: "", auth_type: "PASSWORD" });
        fetchGateways();
      } else {
        alert("Failed to add Gateway");
      }
    } catch (e) {
      alert("Network Error: Make sure the Backend is running.");
    }
  };

  const handleDeleteGateway = async (id: string) => {
    if(!confirm("Are you sure you want to delete this Gateway?")) return;
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/sip-gateways/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) fetchGateways();
    } catch(e) {
        alert("Failed to delete Gateway");
    }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">SIP Trunks</h1>
          <p className="text-muted-foreground">Manage Twilio, SignalWire, or Bring-Your-Own VoIP Providers.</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setIsTestModalOpen(true)} className="bg-emerald-600 text-white hover:bg-emerald-500 px-5 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2 shadow-[0_0_20px_rgba(16,185,129,0.2)]">
            <Zap className="w-4 h-4 fill-current" />
            Test Trunk
          </button>
          <button onClick={() => setIsModalOpen(true)} className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
            <Plus className="w-4 h-4" />
            Add Gateway
          </button>
        </div>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              <th className="font-medium text-muted-foreground p-4">Provider Name</th>
              <th className="font-medium text-muted-foreground p-4">Host</th>
              <th className="font-medium text-muted-foreground p-4">Auth Username</th>
              <th className="font-medium text-muted-foreground p-4">Type</th>
              <th className="font-medium text-muted-foreground p-4">Status</th>
              <th className="font-medium text-muted-foreground p-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {gateways.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-12 text-center text-muted-foreground">
                  <PhoneCall className="w-8 h-8 opacity-50 mx-auto mb-3" />
                  No SIP Gateways connected. Without a trunk, FreeSWITCH cannot dial out.
                </td>
              </tr>
            ) : (
              gateways.map((trunk) => (
                <tr key={trunk.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                  <td className="p-4 font-medium text-white">{trunk.name}</td>
                  <td className="p-4 text-neutral-300 font-mono text-sm">{trunk.sip_server}</td>
                  <td className="p-4 text-muted-foreground font-mono text-sm">{trunk.sip_username || '—'}</td>
                  <td className="p-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border
                      ${trunk.auth_type === 'IP_BASED' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' : 'bg-purple-500/10 text-purple-400 border-purple-500/20'}`}>
                      {trunk.auth_type === 'IP_BASED' ? 'IP AUTH' : 'REGISTRATION'}
                    </span>
                  </td>
                  <td className="p-4">
                    {(() => {
                      const st = gwStatuses[trunk.id];
                      const state = st?.sofia_state || 'UNKNOWN';
                      const statusColors: Record<string, string> = {
                        REGED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
                        NOREG: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                        FAIL_WAIT: 'bg-red-500/10 text-red-400 border-red-500/20',
                        TRYING: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
                        UNREGED: 'bg-red-500/10 text-red-400 border-red-500/20',
                        UNKNOWN: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
                      };
                      const labels: Record<string, string> = {
                        REGED: 'REGISTERED',
                        NOREG: 'NO REG (IP)',
                        FAIL_WAIT: 'DOWN',
                        TRYING: 'CONNECTING',
                        UNREGED: 'UNREGISTERED',
                        UNKNOWN: 'UNKNOWN',
                      };
                      const css = statusColors[state] || statusColors.UNKNOWN;
                      const label = labels[state] || state;
                      return (
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${css}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            state === 'REGED' || state === 'NOREG' ? 'bg-emerald-400' : state === 'TRYING' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
                          }`} />
                          {label}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="p-4 text-right flex justify-end gap-3">
                    <button onClick={() => handleDeleteGateway(trunk.id)} className="text-xs font-medium text-destructive-foreground hover:text-red-400 transition-colors bg-red-500/10 px-2.5 py-1 rounded-md">Delete</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center p-6 border-b border-white/5">
              <h2 className="text-xl font-semibold text-white">Add SIP Gateway</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-muted-foreground hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <form onSubmit={handleAddGateway} className="p-6 space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Provider Name</label>
                <input type="text" placeholder="e.g. Twilio, SignalWire, BitCall" value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">SIP Host / Domain</label>
                <input type="text" placeholder="e.g. gateway.provider.io" value={formData.host} onChange={(e) => setFormData({...formData, host: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
              </div>

              {/* Auth Type Toggle */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Authentication Method</label>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setFormData({...formData, auth_type: 'PASSWORD'})}
                    className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                      formData.auth_type === 'PASSWORD' ? 'bg-purple-500/10 border-purple-500/30 text-purple-400' : 'bg-black/30 border-white/10 text-muted-foreground hover:border-white/20'
                    }`}>
                    Username / Password
                  </button>
                  <button type="button" onClick={() => setFormData({...formData, auth_type: 'IP_BASED'})}
                    className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                      formData.auth_type === 'IP_BASED' ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-black/30 border-white/10 text-muted-foreground hover:border-white/20'
                    }`}>
                    IP Authentication
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {formData.auth_type === 'IP_BASED'
                    ? 'Your provider authenticates by server IP address. No registration required.'
                    : 'FreeSWITCH sends a SIP REGISTER with these credentials.'}
                </p>
              </div>

              {formData.auth_type === 'PASSWORD' && (
                <>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Auth Username</label>
                    <input type="text" placeholder="Username" value={formData.username} onChange={(e) => setFormData({...formData, username: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Auth Password</label>
                    <input type="password" placeholder="Password" value={formData.sip_password} onChange={(e) => setFormData({...formData, sip_password: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
                  </div>
                </>
              )}
              
              <div className="pt-4 flex justify-end gap-3">
                <button type="button" onClick={() => setIsModalOpen(false)} className="px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-white/5 transition-colors text-white">Cancel</button>
                <button type="submit" className="bg-emerald-500 hover:bg-emerald-400 text-black px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors shadow-[0_0_15px_rgba(16,185,129,0.2)]">Connect Trunk</button>
              </div>
            </form>
          </div>
        </div>
      )}
      
      <TestTrunkModal 
        isOpen={isTestModalOpen} 
        onClose={() => setIsTestModalOpen(false)} 
        gateways={gateways} 
      />
    </div>
  );
}

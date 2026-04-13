'use client';

import { useState } from 'react';
import { Loader2, Phone, X, Zap, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function TestTrunkModal({ isOpen, onClose, gateways }: { isOpen: boolean, onClose: () => void, gateways: any[] }) {
  const [gatewayId, setGatewayId] = useState('');
  const [targetNumber, setTargetNumber] = useState('');
  const [status, setStatus] = useState<'idle' | 'pinging' | 'success' | 'failed'>('idle');
  const [debugInfo, setDebugInfo] = useState<string | null>(null);

  // Auto-select on open
  if (isOpen && !gatewayId && gateways.length > 0) {
    setGatewayId(gateways[0].id);
  }

  if (!isOpen) return null;

  const handleTestCall = async () => {
    if (!gatewayId || !targetNumber) {
      alert("Please select a trunk and enter a target number.");
      return;
    }

    setStatus('pinging');
    setDebugInfo(null);

    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      const res = await fetch(`${API_BASE}/sip-gateways/${gatewayId}/test?target_number=${encodeURIComponent(targetNumber)}`, {
        method: 'POST'
      });

      const data = await res.json();

      if (res.ok) {
        setStatus(data.status === 'success' ? 'success' : 'failed');
        setDebugInfo(data.detail || JSON.stringify(data));
      } else {
        setStatus('failed');
        setDebugInfo(data.detail || "Server error occurred");
      }
    } catch (err: any) {
      setStatus('failed');
      setDebugInfo(err.message || "Network request failed");
    }
  };

  const handleClose = () => {
    setStatus('idle');
    setDebugInfo(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#0a0a0f] border border-white/10 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between p-5 border-b border-white/10 bg-white/5">
          <div className="flex items-center gap-3 text-white">
            <div className="p-2 bg-emerald-500/20 rounded-lg">
              <Zap className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h3 className="font-semibold text-lg">Test SIP Trunk</h3>
              <p className="text-xs text-zinc-400">Ping your gateway to verify outbound audio routing.</p>
            </div>
          </div>
          {status !== 'pinging' && (
            <button onClick={handleClose} className="p-2 text-zinc-400 hover:text-white transition-colors hover:bg-white/10 rounded-lg">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        <div className="p-6 space-y-5">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5 focus:text-emerald-400 transition-colors">
                Select SIP Trunk
              </label>
              <select
                disabled={status === 'pinging'}
                value={gatewayId}
                onChange={(e) => setGatewayId(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors disabled:opacity-50"
              >
                <option value="" disabled className="bg-zinc-900">-- Choose Trunk --</option>
                {gateways.map(g => (
                  <option key={g.id} value={g.id} className="bg-zinc-900">{g.name} ({g.sip_server})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                Target Destination
              </label>
              <input
                disabled={status === 'pinging'}
                type="text"
                placeholder="Phone number or SIP URI"
                value={targetNumber}
                onChange={e => setTargetNumber(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-medium text-white placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500 transition-colors"
              />
              <p className="text-xs text-zinc-500 mt-2">Example: 18005551212 or username@sip2sip.info</p>
            </div>
          </div>

          {/* Debug Area */}
          {status !== 'idle' && status !== 'pinging' && (
            <div className="mt-2 border border-white/10 rounded-lg bg-black overflow-hidden animate-in slide-in-from-bottom-2">
                <div className="bg-white/5 px-4 py-2 border-b border-white/10 flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${status === 'success' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`} />
                <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold font-mono">
                    {status === 'success' ? 'Ping Successful' : 'Ping Failed'}
                </span>
                </div>
                <div className="p-4 overflow-y-auto font-mono text-[11px] space-y-1">
                    <span className="text-zinc-500">[{new Date().toLocaleTimeString()}]</span> <span className={`${status === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>[TRUNK]</span>
                    <span className="text-zinc-300 ml-2 break-words whitespace-pre-wrap">{debugInfo}</span>
                </div>
            </div>
          )}
        </div>

        <div className="p-5 border-t border-white/10 bg-black/20 flex gap-3">
          {status === 'pinging' ? (
            <div className="flex-1 w-full px-4 py-2.5 flex items-center justify-center gap-2 border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 rounded-lg text-sm font-medium font-mono animate-pulse">
              <Loader2 className="w-4 h-4 animate-spin" /> Pinging Gateway...
            </div>
          ) : (
            <>
              <button
                onClick={handleClose}
                className="flex-1 py-2.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 transition-colors text-sm font-medium"
              >
                Close
              </button>
              <button
                disabled={!targetNumber || !gatewayId}
                onClick={handleTestCall}
                className="flex-[1.5] py-2.5 rounded-lg font-medium transition-colors bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 flex items-center justify-center gap-2 text-sm shadow-[0_0_15px_rgba(16,185,129,0.3)]"
              >
                <Zap className="w-4 h-4 fill-current" /> Ping Trunk
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

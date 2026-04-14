"use client";

import { Plus, UserCircle, ShieldCheck, Trash } from "lucide-react";
import { useState, useEffect } from "react";

export default function CallerIdsPage() {
  const [callerIds, setCallerIds] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({ name: "", num: "" });

  const fetchCallerIds = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/caller-ids`);
      if (res.ok) setCallerIds(await res.json());
    } catch(e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchCallerIds();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.num) {
      alert("Both Name and Phone Number are required.");
      return;
    }

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/caller-ids`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: formData.name, phone_number: formData.num })
      });
      if (res.ok) {
        setIsModalOpen(false);
        setFormData({ name: "", num: "" });
        fetchCallerIds();
      } else {
        alert("Failed to add Caller ID");
      }
    } catch(e) {
      alert("Failed to add Caller ID");
    }
  };

  const handleDelete = async (id: string) => {
    if(!confirm("Delete this Caller ID?")) return;
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/caller-ids/${id}`, { method: 'DELETE' });
      if (res.ok) fetchCallerIds();
    } catch(e) {
      alert("Failed to delete Caller ID");
    }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-[1400px] mx-auto relative z-10">
      
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-10 gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Caller IDs</h1>
          <p className="text-muted-foreground">Manage authorized Caller Identification numbers to be attached to outbound arrays.</p>
        </div>
        <button onClick={() => setIsModalOpen(true)} className="bg-white text-black hover:bg-neutral-200 px-6 py-3 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
          <Plus className="w-5 h-5" />
          Add Caller ID
        </button>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead>
              <tr className="border-b border-white/10 bg-black/20 text-muted-foreground text-xs uppercase tracking-wider font-semibold">
                <th className="p-4 pl-6">Profile Descriptor</th>
                <th className="p-4">Outbound Phone Number</th>
                <th className="p-4">STIR/SHAKEN Status</th>
                <th className="p-4">Date Added</th>
                <th className="p-4 text-right pr-6">Management</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={5} className="text-center p-8 text-neutral-500">Loading Caller IDs...</td></tr>
              ) : callerIds.length === 0 ? (
                <tr><td colSpan={5} className="text-center p-8 text-neutral-500">No Caller IDs registered.</td></tr>
              ) : callerIds.map((cid) => (
                <tr key={cid.id} className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                  <td className="p-4 pl-6 font-medium text-white flex items-center gap-3">
                     <UserCircle className="w-5 h-5 text-emerald-400" />
                     {cid.name}
                  </td>
                  <td className="p-4 font-mono tracking-tight text-white/90">
                     {cid.phone_number}
                  </td>
                  <td className="p-4">
                     <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                         <ShieldCheck className="w-3.5 h-3.5" /> Approved
                     </span>
                  </td>
                  <td className="p-4 text-muted-foreground">{new Date(cid.created_at).toLocaleDateString()}</td>
                  <td className="p-4 text-right pr-6">
                    <button onClick={() => handleDelete(cid.id)} className="text-xs font-medium text-destructive-foreground hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 p-2">
                       Delete Profile
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-sm shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center p-6 border-b border-white/5">
              <h2 className="text-xl font-semibold text-white">Add Caller ID</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-muted-foreground hover:text-white transition-colors">
                 <UserCircle className="w-5 h-5" />
              </button>
            </div>
            
            <form onSubmit={handleAdd} className="p-6 space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Profile Name</label>
                <input type="text" placeholder="e.g. Sales Line" value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Phone Number</label>
                <input type="text" placeholder="e.g. +1..." value={formData.num} onChange={(e) => setFormData({...formData, num: e.target.value})} className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500/50 transition-colors" />
              </div>
              
              <div className="pt-4 flex justify-end gap-3">
                 <button type="button" onClick={() => setIsModalOpen(false)} className="px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-white/5 transition-colors text-white">Cancel</button>
                 <button type="submit" className="bg-emerald-500 hover:bg-emerald-400 text-black px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors shadow-[0_0_15px_rgba(16,185,129,0.2)]">Provision</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { Activity, Play, Pause, PowerOff, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function CampaignsPage() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<any[]>([]);

  const fetchCampaigns = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/campaigns/`);
      if (res.ok) {
        setCampaigns(await res.json());
      }
    } catch(e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchCampaigns();
    const interval = setInterval(() => {
        fetchCampaigns();
    }, 5000); // Poll every 5s for live metric updates on table
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (e: React.MouseEvent, id: string, action: string) => {
      e.stopPropagation(); // Prevent row click routing
      try {
          if (action === 'delete') {
              if(!confirm("Are you sure you want to completely destroy this Campaign instance?")) return;
              await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/campaigns/${id}`, { method: 'DELETE' });
          } else {
              await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/campaigns/${id}/${action}`, { method: 'POST' });
          }
          fetchCampaigns(); // Insta-refresh table
      } catch (err) {
          alert(`Failed to execute engine control: ${action}`);
      }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Campaigns</h1>
          <p className="text-muted-foreground">Manage active dialing loops and execution states.</p>
        </div>
        <Link href="/campaigns/new" className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
          New Campaign
        </Link>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              <th className="font-medium text-muted-foreground p-4">Name</th>
              <th className="font-medium text-muted-foreground p-4">Status</th>
              <th className="font-medium text-muted-foreground p-4">Contacts</th>
              <th className="font-medium text-muted-foreground p-4">Dialed</th>
              <th className="font-medium text-muted-foreground p-4">Transfers</th>
              <th className="font-medium text-muted-foreground p-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted-foreground">
                  No campaigns initialized yet.
                </td>
              </tr>
            ) : (
              campaigns.map((camp) => (
                <tr key={camp.id} className="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer" onClick={() => router.push(`/campaigns/${camp.id}`)}>
                  <td className="p-4 font-medium text-white hover:text-emerald-400 transition-colors">{camp.name}</td>
                  <td className="p-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border
                      ${camp.status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 
                        camp.status === 'PAUSED' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 
                        'bg-neutral-500/10 text-neutral-400 border-neutral-500/20'}`}>
                      {camp.status === 'ACTIVE' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
                      {camp.status}
                    </span>
                    {camp.enable_dynamic_caller_id && (
                      <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                        ⚡ Dynamic CID
                      </span>
                    )}
                  </td>
                  <td className="p-4 text-muted-foreground">{camp.total_contacts}</td>
                  <td className="p-4 text-muted-foreground">{camp.dialed_count}</td>
                  <td className="p-4 text-emerald-400 font-medium">{camp.transferred_count}</td>
                  <td className="p-4 text-right flex gap-2 justify-end">
                    {camp.status !== 'ACTIVE' && (
                      <button onClick={(e) => handleAction(e, camp.id, 'start')} className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors" title="Start Dialing">
                        <Play className="w-4 h-4" />
                      </button>
                    )}
                    {camp.status === 'ACTIVE' && (
                      <button onClick={(e) => handleAction(e, camp.id, 'pause')} className="p-2 rounded-lg bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors" title="Pause Dialing">
                        <Pause className="w-4 h-4" />
                      </button>
                    )}
                    <button onClick={(e) => handleAction(e, camp.id, 'delete')} className="p-2 rounded-lg bg-destructive/10 text-destructive-foreground hover:bg-destructive/20 transition-colors" title="Delete Campaign">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

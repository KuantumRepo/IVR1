'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Plus, Play, Trash2, GitBranch, Loader2, PhoneCall, Workflow, AlertCircle } from 'lucide-react';
import { useRouter } from 'next/navigation';
import TestFlowModal from './TestFlowModal';

export default function ScriptsClient({ initialScripts }: { initialScripts: any[] }) {
  const router = useRouter();
  const [scripts, setScripts] = useState(initialScripts);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete the flow script "${name}"? This cannot be undone and may break campaigns relying on it.`)) return;

    setDeletingId(id);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      const res = await fetch(`${API_BASE}/call-scripts/${id}`, { method: 'DELETE' });
      
      if (res.ok) {
        setScripts(prev => prev.filter(s => s.id !== id));
        router.refresh();
      } else {
        alert("Failed to delete script");
      }
    } catch (e) {
      console.error(e);
      alert("Error deleting script");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">IVR Flow Scripts</h1>
          <p className="text-muted-foreground">Visual node-based call trees — drag, connect, deploy.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsTestModalOpen(true)}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2 shadow-[0_0_20px_rgba(99,102,241,0.2)]"
          >
            <Play className="w-4 h-4 fill-current" />
            Test Flow
          </button>
          <Link
            href="/scripts/new"
            className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]"
          >
            <Plus className="w-4 h-4" />
            New Flow
          </Link>
        </div>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-zinc-300">
            <thead className="text-xs uppercase bg-white/5 border-b border-white/10 text-zinc-400">
              <tr>
                <th className="px-6 py-4 font-semibold tracking-wider">Flow Name</th>
                <th className="px-6 py-4 font-semibold tracking-wider">Type</th>
                <th className="px-6 py-4 font-semibold tracking-wider">Complexity</th>
                <th className="px-6 py-4 font-semibold tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {scripts.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-20 text-center text-zinc-500">
                    <Workflow className="w-12 h-12 mx-auto mb-4 opacity-20" />
                    <p className="text-lg font-medium text-white mb-1">No flows designed yet</p>
                    <p className="text-sm">Create a new interactive voice flow to get started.</p>
                  </td>
                </tr>
              ) : (
                scripts.map((script) => {
                  const totalRoutes = script.nodes?.reduce((acc: number, n: any) => acc + (n.routes?.length ?? 0), 0) ?? 0;
                  const totalNodes = script.nodes?.length ?? 0;

                  return (
                    <tr key={script.id} className="hover:bg-white/[0.02] transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex flex-col">
                          <span className="font-medium text-white text-base">{script.name}</span>
                          {script.description && (
                            <span className="text-xs text-zinc-500 mt-0.5 max-w-[300px] truncate">
                              {script.description}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 border border-white/5">
                          <PhoneCall className="w-3 h-3" />
                          {script.script_type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3 text-xs text-zinc-400">
                          <span className="flex items-center gap-1.5 bg-blue-500/10 text-blue-400 px-2 py-1 rounded border border-blue-500/20">
                            <Workflow className="w-3.5 h-3.5" />
                            {totalNodes} Nodes
                          </span>
                          <span className="flex items-center gap-1.5 bg-emerald-500/10 text-emerald-400 px-2 py-1 rounded border border-emerald-500/20">
                            <GitBranch className="w-3.5 h-3.5" />
                            {totalRoutes} Routes
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2 opacity-80 group-hover:opacity-100 transition-opacity">
                          <Link
                            href={`/scripts/new?edit=${script.id}`}
                            className="px-3 py-1.5 text-xs font-medium bg-white/5 hover:bg-white/10 border border-white/10 rounded-md transition-colors text-white"
                          >
                            Edit
                          </Link>
                          <button
                            onClick={() => handleDelete(script.id, script.name)}
                            disabled={deletingId === script.id}
                            className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-colors disabled:opacity-50"
                            title="Delete Script"
                          >
                            {deletingId === script.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <TestFlowModal 
        isOpen={isTestModalOpen} 
        onClose={() => setIsTestModalOpen(false)} 
        scripts={scripts} 
      />
    </div>
  );
}

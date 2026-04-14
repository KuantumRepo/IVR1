"use client";

import { useWebSocket } from "@/providers/WebSocketProvider";

export function LiveMetrics() {
  const { stats } = useWebSocket();

  return (
    <div className="bg-background/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium hover:border-white/20 transition-colors">
       <span className="text-muted-foreground">Active Dials:</span>
       <span className="text-white animate-soft-pulse text-lg">{stats.activeCalls}</span>
    </div>
  );
}

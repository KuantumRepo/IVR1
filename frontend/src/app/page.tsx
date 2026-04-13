"use client";

import { useWebSocket } from "@/providers/WebSocketProvider";
import { LiveEventFeed } from "@/components/dashboard/live-event-feed";
import { LiveChart } from "@/components/dashboard/live-chart";
import Link from "next/link";
import { Play } from "lucide-react";

export default function Dashboard() {
  const { isConnected, stats } = useWebSocket();

  return (
    <div className="p-8 pb-20 sm:p-12 font-[family-name:var(--font-geist-sans)] max-w-7xl mx-auto w-full relative z-10">
      <div className="flex justify-between items-center mb-8 bg-background/40 backdrop-blur-md p-6 rounded-2xl border border-white/5 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className={`w-4 h-4 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-500'} absolute top-0 left-0 z-10`}></div>
            <div className={`w-4 h-4 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-red-500'} absolute top-0 left-0`}></div>
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Live Engine</h1>
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              Status: <span className={isConnected ? "text-emerald-400 font-medium" : "text-red-400 font-medium"}>
                {isConnected ? "Connected & Routing" : "Disconnected"}
              </span>
            </p>
          </div>
        </div>
        <div className="flex gap-4">
          <Link href="/campaigns/new" className="bg-white text-black hover:bg-neutral-200 px-6 py-2.5 rounded-lg flex items-center gap-2 font-medium transition-transform active:scale-95 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
            <Play className="w-4 h-4" /> Start Dialing
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="bg-background/60 backdrop-blur-xl border border-white/10 p-6 rounded-2xl hover:border-white/20 transition-all duration-300 relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          <h3 className="text-sm font-medium text-muted-foreground mb-4">Concurrent Active Calls</h3>
          <div className="text-5xl font-semibold tracking-tight text-emerald-400">{stats.activeCalls}</div>
          <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live across all campaigns
          </p>
        </div>
        
        <div className="bg-background/60 backdrop-blur-xl border border-white/10 p-6 rounded-2xl hover:border-white/20 transition-all duration-300 relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          <h3 className="text-sm font-medium text-muted-foreground mb-4">Total Answered (Session)</h3>
          <div className="text-5xl font-semibold tracking-tight text-white">{stats.totalAnswered}</div>
          <p className="text-xs text-muted-foreground mt-3">Since dashboard opened</p>
        </div>

        <div>
          <LiveChart />
        </div>
      </div>

      <div className="h-[400px]">
        <LiveEventFeed />
      </div>

    </div>
  );
}

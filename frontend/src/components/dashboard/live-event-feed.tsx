"use client";

import React from "react";
import { useWebSocket } from "@/providers/WebSocketProvider";

export function LiveEventFeed() {
  const { events } = useWebSocket();

  return (
    <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden flex flex-col h-full hover:border-white/20 transition-all duration-300">
      <div className="p-6 border-b border-white/10 bg-white/5 flex items-center justify-between">
        <h3 className="text-lg font-medium text-white tracking-tight flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          Live Event Feed
        </h3>
        <span className="text-xs text-muted-foreground bg-white/5 px-2 py-1 rounded-md border border-white/10">
          WS Connected
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
        {events.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            Awaiting calls...
          </div>
        ) : (
          events.map((ev, i) => (
            <div 
              key={i} 
              className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors"
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center border ${
                  ev.event === 'CALL_STARTED' ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' :
                  ev.cause === 'NORMAL_CLEARING' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                  'bg-rose-500/10 border-rose-500/20 text-rose-400'
                }`}>
                  {ev.event === 'CALL_STARTED' ? (
                    <svg className="w-4 h-4" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                  ) : (
                    <svg className="w-4 h-4" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91"/><line x1="22" x2="2" y1="2" y2="22"/></svg>
                  )}
                </div>
                <div className="flex flex-col overflow-hidden">
                  <span className="text-sm font-medium text-white truncate">
                    {ev.phone_number || "Unknown Target"}
                  </span>
                  <span className="text-xs text-muted-foreground truncate flex items-center gap-1.5">
                    {ev.campaign_name && <span className="max-w-[120px] truncate">{ev.campaign_name}</span>}
                    {ev.campaign_name && <span className="opacity-50">•</span>}
                    {ev.event === 'CALL_STARTED' ? 'Dialing out' : ev.cause}
                  </span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground shrink-0 border border-white/5 bg-black/20 px-2 py-1 rounded">
                {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString('en-US', { hour12: false }) : 'Just now'}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

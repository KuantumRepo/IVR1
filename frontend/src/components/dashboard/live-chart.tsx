import React from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useWebSocket } from "@/providers/WebSocketProvider";

export function LiveChart() {
  const { stats } = useWebSocket();

  return (
    <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-6 h-full hover:border-white/20 transition-all duration-300">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="text-lg font-medium text-white tracking-tight">Call Velocity</h3>
          <p className="text-xs text-muted-foreground mt-1">Calls per second (last 60s)</p>
        </div>
        <div className="flex items-end gap-2">
          <span className="text-3xl font-semibold tracking-tight text-emerald-400">
            {stats.cpsHistory[stats.cpsHistory.length - 1]?.count || 0}
          </span>
          <span className="text-sm text-muted-foreground mb-1">CPS</span>
        </div>
      </div>

      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={stats.cpsHistory}>
            <defs>
              <linearGradient id="colorCps" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis 
              dataKey="time" 
              hide={true} // Hide exact times for cleaner look
            />
            <YAxis 
              hide={true} 
              domain={[0, 'dataMax + 2']} // Leave headroom
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'rgba(0,0,0,0.8)', 
                borderColor: 'rgba(255,255,255,0.1)',
                borderRadius: '8px',
                color: '#fff'
              }}
              itemStyle={{ color: '#34d399' }}
              labelStyle={{ color: '#888' }}
            />
            <Area 
              type="monotone" 
              dataKey="count" 
              name="Calls"
              stroke="#34d399" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorCps)" 
              isAnimationActive={false} // Disable recharts animation to prevent jitter on 1s ticks
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

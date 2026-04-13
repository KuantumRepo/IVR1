"use client";

import React, { createContext, useContext, useEffect, useState, useRef } from "react";

export type WebSocketEvent = {
  event: string;
  campaign_id?: string;
  campaign_name?: string;
  phone_number?: string;
  timestamp?: string;
  cause?: string;
};

interface DashboardStats {
  activeCalls: number;
  totalAnswered: number;
  cpsHistory: { time: string; count: number }[];
}

interface WebSocketContextType {
  isConnected: boolean;
  events: WebSocketEvent[];
  stats: DashboardStats;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  // We initialize the chart with 60 seconds of zero values
  const [stats, setStats] = useState<DashboardStats>({
    activeCalls: 0,
    totalAnswered: 0,
    cpsHistory: Array.from({ length: 60 }).map((_, i) => ({ 
      time: `-${60 - i}s`, 
      count: 0 
    }))
  });

  const ws = useRef<WebSocket | null>(null);
  
  // Track CPS natively
  const callsInCurrentSecond = useRef(0);
  const cpsInterval = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host; // e.g., localhost or app.domain.com
      ws.current = new WebSocket(`${protocol}//${host}/ws/dashboard`);

      ws.current.onopen = () => {
        setIsConnected(true);
      };

      ws.current.onclose = () => {
        setIsConnected(false);
        setTimeout(connect, 3000);
      };

      ws.current.onmessage = (message) => {
        try {
          const rawData = JSON.parse(message.data);
          
          // Redis passes the message embedded in a data/event object. 
          // If the nested payload is a stringified JSON, parse it:
          let payload;
          if (typeof rawData.event === 'string' && rawData.event.startsWith('{')) {
             payload = JSON.parse(rawData.event);
          } else {
             payload = rawData.event || rawData;
          }
          
          if (!payload.event) return;

          const event = payload as WebSocketEvent;

          // Push event onto the top of the stack, max 50 events
          setEvents(prev => [event, ...prev].slice(0, 50));

          if (event.event === "CALL_STARTED") {
            callsInCurrentSecond.current += 1;
            setStats(prev => ({ ...prev, activeCalls: prev.activeCalls + 1 }));
          } else if (event.event === "CALL_ENDED") {
            setStats(prev => ({ 
              ...prev, 
              // Don't let active calls accidentally dip below zero if we just started tracking
              activeCalls: Math.max(0, prev.activeCalls - 1),
              totalAnswered: event.cause === "NORMAL_CLEARING" ? prev.totalAnswered + 1 : prev.totalAnswered
            }));
          }
        } catch (e) {
          console.error("Failed to parse WS message", e);
        }
      };
    }

    connect();

    // The ticker that shifts the CPS chart 1 second per tick
    cpsInterval.current = setInterval(() => {
      setStats(prev => {
        const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false, second: '2-digit', minute: '2-digit' });
        const newHistory = [...prev.cpsHistory.slice(1), { 
          time: timeStr, 
          count: callsInCurrentSecond.current 
        }];
        callsInCurrentSecond.current = 0; // reset for next second
        return { ...prev, cpsHistory: newHistory };
      });
    }, 1000);

    return () => {
      if (ws.current) {
        ws.current.onclose = null;
        ws.current.close();
      }
      if (cpsInterval.current) clearInterval(cpsInterval.current);
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ isConnected, events, stats }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
}

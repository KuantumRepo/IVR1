"use client";

import { useEffect, useState } from "react";

export function LiveMetrics() {
  const [activeDials, setActiveDials] = useState(0);

  useEffect(() => {
    // Connect to the FastAPI WebSocket port mapped locally
    const ws = new WebSocket("ws://localhost:8000/ws/dashboard");
    
    ws.onmessage = (event) => {
       try {
           const data = JSON.parse(event.data);
           if (data.event === "CALL_STARTED") {
               setActiveDials(prev => prev + 1);
           }
           if (data.event === "CALL_ENDED") {
               setActiveDials(prev => Math.max(0, prev - 1));
           }
       } catch (err) {
           console.error("Payload parse error", err);
       }
    };

    return () => {
        ws.close();
    };
  }, []);

  return (
    <div className="bg-background/60 backdrop-blur-xl border border-white/10 px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium hover:border-white/20 transition-colors">
       <span className="text-muted-foreground">Active Dials:</span>
       <span className="text-white animate-soft-pulse text-lg">{activeDials}</span>
    </div>
  );
}

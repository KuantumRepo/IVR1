"use client";

import { useState, use } from "react";
import { Phone, ArrowLeft, Radio, Terminal } from "lucide-react";
import Link from "next/link";

export default function GatewayTestWizard({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [status, setStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [log, setLog] = useState<string[]>([]);
  
  const addLog = (line: string) => setLog(prev => [...prev, line]);

  const handleTestCall = async () => {
      if (!phoneNumber) return;
      
      setStatus("testing");
      setLog([]);
      addLog(`[INIT] Sending test originate to FreeSWITCH...`);
      addLog(`[TARGET] ${phoneNumber}`);
      addLog(`[GATEWAY] ${resolvedParams.id}`);
      
      try {
          const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1'}/sip-gateways/${resolvedParams.id}/test?target_number=${encodeURIComponent(phoneNumber)}`, {
              method: 'POST'
          });
          
          const body = await res.json().catch(() => ({}));
          
          if (!res.ok) {
              addLog(`[HTTP ${res.status}] ${body.detail || "Server error"}`);
              setStatus("error");
              return;
          }
          
          // Show the real FreeSWITCH response
          addLog(`[DIAL] ${body.dial_string || "unknown"}`);
          
          if (body.status === "success") {
              addLog(`[FreeSWITCH] ${body.detail}`);
              addLog(`[✓] Call connected — phone should be ringing`);
              setStatus("success");
          } else {
              addLog(`[FreeSWITCH] ${body.detail}`);
              addLog(`[✗] Call failed — see error above`);
              setStatus("error");
          }
          
      } catch (err: any) {
          addLog(`[NETWORK ERROR] ${err.message}`);
          setStatus("error");
      }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-4xl mx-auto relative z-10">
      
      <div className="mb-10">
        <Link href="/gateways" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-white transition-colors mb-6">
           <ArrowLeft className="w-4 h-4" /> Back to Trunks
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Trunk Diagnostics</h1>
        <p className="text-muted-foreground">Test SIP routing by placing a real call through FreeSWITCH.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
         <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 h-fit">
            <h3 className="text-lg font-medium text-white mb-6">Test Call</h3>
            
            <div className="space-y-6">
                <div>
                  <label className="text-sm font-medium text-muted-foreground mb-2 block">Destination</label>
                  <div className="relative">
                    <Phone className="w-5 h-5 absolute left-4 top-3.5 text-white/30" />
                    <input 
                      type="text" 
                      value={phoneNumber}
                      onChange={(e) => setPhoneNumber(e.target.value)}
                      className="w-full bg-black/40 border border-white/10 rounded-xl pl-12 pr-4 py-3 text-white focus:outline-none focus:border-white/30 transition-colors font-mono"
                      placeholder="e.g. 18005551212 or user@domain.com"
                    />
                  </div>
                  <p className="text-xs text-white/30 mt-2">
                    Phone number → routes via gateway trunk · SIP URI (user@domain) → direct call
                  </p>
                </div>

                <button 
                  onClick={handleTestCall}
                  disabled={status === "testing" || !phoneNumber}
                  className={`w-full py-3.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center justify-center gap-2 
                     ${status === "testing" ? 'bg-white/10 text-white/50 cursor-not-allowed' : 'bg-emerald-500 text-black hover:bg-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.2)]'}`}
                >
                  <Radio className={`w-5 h-5 ${status === 'testing' && 'animate-pulse'}`} /> 
                  {status === 'testing' ? 'Calling...' : 'Place Test Call'}
                </button>
            </div>
         </div>

         {/* Real Console Output */}
         <div className="bg-black/80 border border-white/10 rounded-2xl p-6 relative overflow-hidden font-mono text-sm leading-relaxed shadow-2xl">
            <div className="flex items-center gap-2 mb-4 border-b border-white/10 pb-4 text-white/50">
               <Terminal className="w-5 h-5" />
               <span>FreeSWITCH Response</span>
            </div>
            
            <div className="space-y-3">
               {log.length === 0 && (
                   <span className="text-white/20">Waiting for test call...</span>
               )}
               {log.map((line, i) => (
                   <div key={i} className={`
                      ${line.includes('ERROR') || line.includes('✗') || line.includes('-ERR') ? 'text-red-400' : ''}
                      ${line.includes('✓') || line.includes('+OK') ? 'text-emerald-400' : ''}
                      ${line.includes('INIT') ? 'text-purple-400' : ''}
                      ${line.includes('DIAL') ? 'text-blue-400' : ''}
                      ${(!line.includes('ERROR') && !line.includes('✓') && !line.includes('✗') && !line.includes('+OK') && !line.includes('-ERR') && !line.includes('INIT') && !line.includes('DIAL')) ? 'text-neutral-300' : ''}
                   `}>
                      <span className="opacity-50 select-none mr-3">{String(i+1).padStart(2, '0')}</span> 
                      {line}
                   </div>
               ))}
               
               {status === "testing" && (
                   <div className="text-emerald-500/50 flex gap-1 mt-4 ml-6">
                      <span className="animate-bounce">.</span><span className="animate-bounce" style={{animationDelay: "0.1s"}}>.</span><span className="animate-bounce" style={{animationDelay: "0.2s"}}>.</span>
                   </div>
               )}
            </div>
         </div>
      </div>
    </div>
  );
}

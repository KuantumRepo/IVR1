import { Handle, Position, NodeProps } from '@xyflow/react';
import { Volume2, FileAudio, Mic, Play, Square, Loader2 } from 'lucide-react';
import { useState, useRef } from 'react';

export function IvrNodeComponent({ data, isConnectable, selected }: NodeProps) {
  const nodeType = (data.node_type as string) || 'PROMPT';
  const isTerminal = nodeType !== 'PROMPT';
  
  const isAudioMode = data.prompt_type === 'audio';
  const hasPrompt = !isTerminal && (isAudioMode ? !!data.prompt_audio_id : !!data.tts_text);
  
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const togglePlay = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger node selection
    if (!hasPrompt || isTerminal) return;
    
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }

    setPlaying(true);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      let url = '';

      if (isAudioMode) {
        url = `${baseUrl}/audio/${data.prompt_audio_id}/stream`;
      } else {
        const res = await fetch(`${baseUrl}/audio/tts/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            text: data.tts_text, 
            voice: data.tts_voice || 'af_heart' 
          })
        });
        if (!res.ok) throw new Error('Preview failed');
        const blob = await res.blob();
        url = URL.createObjectURL(blob);
      }

      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      await audio.play();
    } catch (err) {
      console.error(err);
      setPlaying(false);
    }
  };

  let borderColor = 'border-indigo-500/80';
  let shadowColor = 'shadow-[0_0_30px_rgba(99,102,241,0.25)]';
  if (nodeType === 'TRANSFER') { borderColor = 'border-emerald-500/80'; shadowColor = 'shadow-[0_0_30px_rgba(16,185,129,0.25)]'; }
  if (nodeType === 'HANGUP') { borderColor = 'border-red-500/80'; shadowColor = 'shadow-[0_0_30px_rgba(239,68,68,0.25)]'; }
  if (nodeType === 'DNC') { borderColor = 'border-amber-500/80'; shadowColor = 'shadow-[0_0_30px_rgba(245,158,11,0.25)]'; }

  return (
    <div className={`w-[290px] rounded-2xl border bg-[#0a0a0f]/95 backdrop-blur-3xl shadow-2xl transition-all ${
      selected
        ? `${borderColor} ${shadowColor}`
        : 'border-white/10 hover:border-white/20'
    }`}>
      {/* Input Handle (Top) */}
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={isConnectable}
        style={{ width: 10, height: 10, border: '2px solid #0a0a0f', background: '#71717a' }}
      />

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
        {!isTerminal ? (
            <button 
              onClick={togglePlay}
              title={hasPrompt ? "Play Prompt" : "No prompt configured"}
              className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                !hasPrompt ? 'bg-white/5 border border-white/10 opacity-50 cursor-not-allowed' :
                playing ? 'bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30' :
                data.is_start_node ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 cursor-pointer' : 
                'bg-white/5 border border-white/10 text-zinc-400 hover:bg-white/10 hover:text-white cursor-pointer'
            }`}>
              {playing ? <Square className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
        ) : (
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-white/5 border border-white/10`}>
               {nodeType === 'TRANSFER' && <div className="w-3 h-3 rounded-full bg-emerald-400" />}
               {nodeType === 'HANGUP' && <div className="w-3 h-3 rounded-full bg-red-400" />}
               {nodeType === 'DNC' && <div className="w-3 h-3 rounded-full bg-amber-400" />}
            </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate">{data.name as string || 'Untitled Node'}</p>
          <p className={`text-[10px] uppercase tracking-widest font-medium mt-0.5 ${
            isTerminal ? 'text-zinc-500' :
            data.is_start_node ? 'text-emerald-500' : 'text-zinc-500'
          }`}>
            {isTerminal ? `TERMINAL: ${nodeType}` :
             data.is_start_node ? '● Start Node' : '○ Menu Step'}
          </p>
        </div>
      </div>

      {/* Prompt preview */}
      {!isTerminal ? (
          <div className="px-4 py-3">
            <div className="flex items-center gap-1.5 mb-1.5">
              {isAudioMode
                ? <FileAudio className="w-3 h-3 text-blue-400" />
                : <Mic className="w-3 h-3 text-purple-400" />
              }
              <span className={`text-[10px] font-semibold uppercase tracking-wider ${
                isAudioMode ? 'text-blue-400' : 'text-purple-400'
              }`}>
                {isAudioMode ? 'Audio File' : 'TTS'}
              </span>
            </div>
            <div className="text-[11px] text-zinc-400 bg-white/3 border border-white/5 rounded-lg px-2.5 py-2 leading-relaxed break-words min-h-[40px]">
              {!hasPrompt ? (
                <span className="italic text-zinc-600">No prompt configured...</span>
              ) : isAudioMode ? (
                <span className="text-blue-300 font-mono">{data.prompt_audio_name as string || data.prompt_audio_id as string}</span>
              ) : (
                <span>"{data.tts_text as string}"</span>
              )}
            </div>
          </div>
      ) : (
          <div className="px-4 py-3">
            <div className="text-[11px] text-zinc-500 italic">
               This edge concludes the routing topology. Caller is disconnected from the IVR bridge.
            </div>
          </div>
      )}

      {/* Output Handle (Bottom) */}
      {!isTerminal && (
          <Handle
            type="source"
            position={Position.Bottom}
            isConnectable={isConnectable}
            style={{ width: 10, height: 10, border: '2px solid #0a0a0f', background: '#6366f1' }}
          />
      )}
    </div>
  );
}

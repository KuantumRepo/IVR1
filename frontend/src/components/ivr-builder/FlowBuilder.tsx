'use client';

import { useCallback, useState, useEffect } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  type Connection,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { v4 as uuidv4 } from 'uuid';
import { IvrNodeComponent } from './IvrNodeComponent';
import { ArrowLeft, Save, Plus, FileAudio, Mic, PhoneCall, PhoneOff, GitBranch, Ban, ChevronDown, Loader2, Play, Square, Volume2 } from 'lucide-react';
import { useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

// ─── Types ───────────────────────────────────────────────────────────────────

interface AudioFile {
  id: string;
  name: string;
  original_name: string;
}

type PromptType = 'tts' | 'audio';
type NodeType = 'PROMPT' | 'TRANSFER' | 'HANGUP' | 'DNC';

const NODE_TYPE_OPTIONS: { value: NodeType; label: string; icon: React.ReactNode; color: string }[] = [
  { value: 'PROMPT',   label: 'Prompt Menu',  icon: <FileAudio  className="w-3.5 h-3.5" />, color: 'text-blue-400'   },
  { value: 'TRANSFER', label: 'Transfer',     icon: <PhoneCall  className="w-3.5 h-3.5" />, color: 'text-emerald-400'},
  { value: 'HANGUP',   label: 'Hangup',       icon: <PhoneOff   className="w-3.5 h-3.5" />, color: 'text-red-400'   },
  { value: 'DNC',      label: 'Add to DNC',   icon: <Ban        className="w-3.5 h-3.5" />, color: 'text-amber-400' },
];

const TTS_VOICES = [
  // American English — Female
  { value: 'af_heart',   label: '🇺🇸 US Female — Heart (Premium)' },
  { value: 'af_bella',   label: '🇺🇸 US Female — Bella' },
  { value: 'af_nova',    label: '🇺🇸 US Female — Nova' },
  { value: 'af_sarah',   label: '🇺🇸 US Female — Sarah' },
  { value: 'af_sky',     label: '🇺🇸 US Female — Sky' },
  // American English — Male
  { value: 'am_adam',    label: '🇺🇸 US Male — Adam' },
  { value: 'am_michael', label: '🇺🇸 US Male — Michael' },
  { value: 'am_echo',    label: '🇺🇸 US Male — Echo' },
  { value: 'am_liam',    label: '🇺🇸 US Male — Liam' },
  // British English — Female
  { value: 'bf_emma',    label: '🇬🇧 UK Female — Emma' },
  { value: 'bf_alice',   label: '🇬🇧 UK Female — Alice' },
  { value: 'bf_lily',    label: '🇬🇧 UK Female — Lily' },
  // British English — Male
  { value: 'bm_george',  label: '🇬🇧 UK Male — George' },
  { value: 'bm_daniel',  label: '🇬🇧 UK Male — Daniel' },
];

// We define initial node structure inside the component to prevent hydration mismatch
const nodeTypes = { ivrNode: IvrNodeComponent };

// ─── Sidebar helpers ──────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500 mb-1.5">
      {children}
    </p>
  );
}

function SidebarInput({ value, onChange, placeholder, className = '' }: {
  value: string; onChange: (v: string) => void; placeholder?: string; className?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors ${className}`}
    />
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function FlowBuilder() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Audio Playback State
  const [playingTTS, setPlayingTTS] = useState<boolean>(false);
  const audioPreviewRef = useRef<HTMLAudioElement | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [scriptName, setScriptName] = useState('New IVR Flow');
  const [audioFiles, setAudioFiles] = useState<AudioFile[]>([]);
  const [audioLoading, setAudioLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Fetch audio library once on mount
  useEffect(() => {
    setMounted(true);
    
    setAudioLoading(true);
    fetch('/api/v1/audio/')
      .then(r => r.json())
      .then(data => setAudioFiles(Array.isArray(data) ? data : []))
      .catch(() => setAudioFiles([]))
      .finally(() => setAudioLoading(false));
      
    // Check if we are in Edit Mode
    if (typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        const editId = urlParams.get('edit');
        
        if (editId) {
            fetch(`/api/v1/call-scripts/${editId}`)
              .then(r => {
                  if (!r.ok) throw new Error("Script not found");
                  return r.json();
              })
              .then(data => {
                  setScriptName(data.name);
                  
                  const loadedNodes: Node[] = [];
                  const loadedEdges: Edge[] = [];
                  
                  // Compute smart automatic layout via tree-traversal levels
                  const nodeLevels = new Map<string, number>();
                  const startNode = data.nodes.find((n: any) => n.is_start_node) || data.nodes[0];
                  
                  if (startNode) {
                      const queue = [{ id: startNode.id, level: 0 }];
                      const visited = new Set<string>();
                      
                      while (queue.length > 0) {
                          const { id, level } = queue.shift()!;
                          if (visited.has(id)) continue;
                          visited.add(id);
                          nodeLevels.set(id, level);
                          
                          const nodeRecord = data.nodes.find((n: any) => n.id === id);
                          if (nodeRecord && nodeRecord.routes) {
                              for (const r of nodeRecord.routes) {
                                  if (r.target_node_id && !visited.has(r.target_node_id)) {
                                      queue.push({ id: r.target_node_id, level: level + 1 });
                                  }
                              }
                          }
                      }
                  }
                  
                  const levelCounts = new Map<number, number>();
                  
                  data.nodes.forEach((n: any) => {
                      const level = nodeLevels.get(n.id) ?? Array.from(nodeLevels.values()).reduce((a,b) => Math.max(a,b), 0) + 1;
                      const indexInLevel = levelCounts.get(level) ?? 0;
                      levelCounts.set(level, indexInLevel + 1);
                      
                      loadedNodes.push({
                          id: n.id,
                          type: 'ivrNode',
                          position: { x: indexInLevel * 380 + 100, y: level * 280 + 100 },
                          data: {
                              name: n.name,
                              node_type: n.node_type || 'PROMPT',
                              is_start_node: n.is_start_node,
                              prompt_type: n.prompt_audio_id ? 'audio' : 'tts',
                              tts_text: n.tts_text || '',
                              tts_voice: n.tts_voice || 'af_heart',
                              prompt_audio_id: n.prompt_audio_id || null,
                              prompt_audio_name: null, 
                          }
                      });
                      
                      n.routes.forEach((route: any) => {
                          if (!route.target_node_id) return;
                          loadedEdges.push({
                              id: uuidv4(),
                              source: n.id,
                              target: route.target_node_id,
                              label: route.key_pressed,
                              animated: true,
                              style: { stroke: 'rgba(255,255,255,0.35)', strokeWidth: 2 },
                              labelStyle: { fill: '#fff', fontWeight: 600, fontSize: 11 },
                              labelBgStyle: { fill: 'rgba(99,102,241,0.25)', borderRadius: 4 },
                          });
                      });
                  });
                  
                  setNodes(loadedNodes);
                  setEdges(loadedEdges);
              })
              .catch(err => {
                  console.error(err);
                  // Load pure defaults if fetch blew up
                  constructDefaultGraph();
              });
        } else {
            constructDefaultGraph();
        }
    }
  }, []);
  
  const constructDefaultGraph = () => {
      setNodes([
        {
          id: uuidv4(),
          type: 'ivrNode',
          position: { x: 280, y: 160 },
          data: {
            name: 'Main Greeting',
            node_type: 'PROMPT',
            is_start_node: true,
            prompt_type: 'tts',
            tts_text: 'Hello! Press 1 to speak with an agent, or press 9 to be removed from our list.',
            tts_voice: 'af_heart',
            prompt_audio_id: null,
            prompt_audio_name: null,
          },
        },
      ]);
  };

  // Keep selectedNode/Edge in sync when nodes/edges change
  useEffect(() => {
    if (selectedNode) {
      const updated = nodes.find(n => n.id === selectedNode.id);
      if (updated) setSelectedNode(updated);
    }
  }, [nodes]);

  useEffect(() => {
    if (selectedEdge) {
      const updated = edges.find(e => e.id === selectedEdge.id);
      if (updated) setSelectedEdge(updated);
    }
  }, [edges]);

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges(eds =>
        addEdge(
          {
            ...params,
            label: '1',
            animated: true,
            style: { stroke: 'rgba(255,255,255,0.35)', strokeWidth: 2 },
            labelStyle: { fill: '#fff', fontWeight: 600, fontSize: 11 },
            labelBgStyle: { fill: 'rgba(99,102,241,0.25)', borderRadius: 4 },
          },
          eds
        )
      ),
    [setEdges]
  );

  const addNode = () => {
    const newNode: Node = {
      id: uuidv4(),
      type: 'ivrNode',
      position: { x: 280 + Math.random() * 200 - 100, y: 350 + nodes.length * 60 },
      data: {
        name: 'New Node',
        node_type: 'PROMPT' as NodeType,
        is_start_node: false,
        prompt_type: 'tts' as PromptType,
        tts_text: '',
        tts_voice: 'af_heart',
        prompt_audio_id: null,
        prompt_audio_name: null,
      },
    };
    setNodes(nds => nds.concat(newNode));
  };

  // ─── Node data updater ─────────────────────────────────────────────────────
  const updateNode = (key: string, value: unknown) => {
    if (!selectedNode) return;
    const updated = { ...selectedNode, data: { ...selectedNode.data, [key]: value } };
    setNodes(nds => nds.map(n => (n.id === selectedNode.id ? updated : n)));
    setSelectedNode(updated);
  };

  // ─── Edge data updater ─────────────────────────────────────────────────────
  const updateEdge = (key: string, value: unknown) => {
    if (!selectedEdge) return;
    const updated = {
      ...selectedEdge,
      ...(key === 'label' ? { label: value as string } : {}),
      data: { ...selectedEdge.data, [key]: value },
    };
    setEdges(eds => eds.map(e => (e.id === selectedEdge.id ? updated : e)));
    setSelectedEdge(updated);
  };

  // ─── Save & compile ────────────────────────────────────────────────────────
  const saveScript = async () => {
    setSaving(true);
    try {
      const payload = {
        name: scriptName,
        script_type: 'PRESS_ONE',
        nodes: nodes.map(n => {
          const nodeEdges = edges.filter(e => e.source === n.id);
          const routes = nodeEdges.map(e => ({
            key_pressed: (e.label as string) || '1',
            target_node_id: e.target,
            response_audio_id: null,
          }));

          return {
            id: n.id,
            name: n.data.name,
            node_type: n.data.node_type,
            is_start_node: n.data.is_start_node,
            // Prompt — one of the two modes, never both
            prompt_audio_id:
              n.data.prompt_type === 'audio' ? (n.data.prompt_audio_id ?? null) : null,
            tts_text:
              n.data.prompt_type === 'tts' ? ((n.data.tts_text as string) || null) : null,
            tts_voice:
              n.data.prompt_type === 'tts' ? (n.data.tts_voice as string) : null,
            routes,
          };
        }),
      };

      const urlParams = new URLSearchParams(window.location.search);
      const editId = urlParams.get('edit');
      const method = editId ? 'PUT' : 'POST';
      const endpoint = editId ? `/api/v1/call-scripts/${editId}` : '/api/v1/call-scripts/';

      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        router.push('/scripts');
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Save failed: ${err.detail || res.statusText}`);
      }
    } catch (err) {
      console.error(err);
      alert('Network error while saving.');
    } finally {
      setSaving(false);
    }
  };

  // ─── Render ────────────────────────────────────────────────────────────────
  if (!mounted) return null; // Avoid hydration mismatch

  const sidebarOpen = !!(selectedNode || selectedEdge);
  const sideData = selectedNode?.data;

  return (
    <div className="w-full h-screen bg-black flex flex-col pt-16">
      {/* ── Top Bar ── */}
      <div className="h-14 border-b border-white/10 bg-black/60 backdrop-blur-xl flex items-center justify-between px-5 z-20 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/scripts" className="p-1.5 hover:bg-white/10 rounded-lg transition-colors">
            <ArrowLeft className="w-4 h-4 text-white" />
          </Link>
          <div className="w-px h-5 bg-white/10" />
          <input
            type="text"
            value={scriptName}
            onChange={e => setScriptName(e.target.value)}
            className="bg-transparent border-none text-base font-semibold text-white focus:outline-none focus:ring-0 w-56"
          />
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={addNode}
            className="flex items-center gap-1.5 text-sm bg-white/8 hover:bg-white/15 border border-white/10 text-white px-3.5 py-1.5 rounded-lg font-medium transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> Add Node
          </button>
          <button
            onClick={saveScript}
            disabled={saving}
            className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 text-white px-4 py-1.5 rounded-lg font-medium transition-colors shadow-[0_0_16px_rgba(99,102,241,0.4)]"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {saving ? 'Saving…' : 'Deploy Script'}
          </button>
        </div>
      </div>

      {/* ── Canvas + Sidebar ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Canvas */}
        <div className="flex-1 relative" style={{ background: '#07070a' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) => { setSelectedNode(node); setSelectedEdge(null); }}
            onEdgeClick={(_, edge) => { setSelectedEdge(edge); setSelectedNode(null); }}
            onPaneClick={() => { setSelectedNode(null); setSelectedEdge(null); }}
            fitView
            colorMode="dark"
            defaultEdgeOptions={{ animated: true }}
          >
            <Background gap={28} size={1.5} color="rgba(255,255,255,0.04)" />
            <Controls
              className="!bg-zinc-900 !border !border-white/10 !rounded-xl !overflow-hidden"
            />
          </ReactFlow>
        </div>

        {/* ── Properties Sidebar ── */}
        <div
          className={`w-[320px] flex-shrink-0 border-l border-white/10 bg-[#0a0a0f]/98 backdrop-blur-3xl flex flex-col transition-all duration-300 overflow-hidden ${
            sidebarOpen ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0 absolute right-0 h-full'
          }`}
        >
          {/* Sidebar scroll body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">

            {/* ── NODE PROPERTIES ── */}
            {selectedNode && sideData && (
              <>
                <div>
                  <Label>Node Name</Label>
                  <SidebarInput
                    value={sideData.name as string}
                    onChange={v => updateNode('name', v)}
                    placeholder="e.g. Main Greeting"
                  />
                </div>

                <div>
                  <Label>Node Type Strategy</Label>
                  <div className="grid grid-cols-2 gap-2 mb-4">
                    {NODE_TYPE_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => updateNode('node_type', opt.value)}
                        className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                          (sideData.node_type || 'PROMPT') === opt.value
                            ? `${opt.color} bg-white/8 border-current/40`
                            : 'text-zinc-500 bg-white/3 border-white/8 hover:text-zinc-300 hover:bg-white/6'
                        }`}
                      >
                        {opt.icon} {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* ── Audio Settings (Available on all modes!) ── */}
                <div className={sideData.node_type !== 'PROMPT' ? "pt-4 border-t border-white/8" : ""}>
                    <Label>{sideData.node_type === 'PROMPT' ? 'Prompt Type' : 'Pre-Action Audio (Optional)'}</Label>
                    {sideData.node_type !== 'PROMPT' && (
                      <p className="text-[10px] text-zinc-500 mb-2 leading-relaxed">
                        This text or audio plays right before the caller is executed as a {(sideData.node_type as string) || 'PROMPT'}.
                      </p>
                    )}
                    <div className="flex bg-black/50 rounded-lg p-1 border border-white/8 gap-1">
                    <button
                      onClick={() => updateNode('prompt_type', 'tts')}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all ${
                        sideData.prompt_type === 'tts'
                          ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                          : 'text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      <Mic className="w-3.5 h-3.5" /> Text to Speech
                    </button>
                    <button
                      onClick={() => updateNode('prompt_type', 'audio')}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all ${
                        sideData.prompt_type === 'audio'
                          ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                          : 'text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      <FileAudio className="w-3.5 h-3.5" /> Audio File
                    </button>
                  </div>
                </div>

                {/* ── TTS panel ── */}
                {sideData.prompt_type === 'tts' && (
                  <>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label>Script Text</Label>
                        <button 
                          onClick={async () => {
                            if (playingTTS) {
                              audioPreviewRef.current?.pause();
                              setPlayingTTS(false);
                              return;
                            }
                            if (!sideData.tts_text) return;
                            setPlayingTTS(true);
                            try {
                              const res = await fetch(`/api/v1/audio/tts/preview`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ 
                                  text: sideData.tts_text, 
                                  voice: sideData.tts_voice || 'af_heart' 
                                })
                              });
                              if (!res.ok) throw new Error('Preview failed');
                              const blob = await res.blob();
                              const url = URL.createObjectURL(blob);
                              if (audioPreviewRef.current) {
                                audioPreviewRef.current.src = url;
                                await audioPreviewRef.current.play();
                              }
                            } catch (e) {
                              console.error(e);
                              setPlayingTTS(false);
                            }
                          }}
                          className={`text-xs px-2.5 py-1 rounded-md mb-1 font-medium flex items-center gap-1.5 transition-colors absolute right-6 ${
                            playingTTS 
                              ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' 
                              : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                          }`}
                        >
                          {playingTTS ? <Square className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                          {playingTTS ? "Stop" : "Audition TTS"}
                        </button>
                      </div>
                      <textarea
                        rows={5}
                        value={(sideData.tts_text as string) || ''}
                        onChange={e => updateNode('tts_text', e.target.value)}
                        placeholder="e.g. Press 1 to speak with an agent, press 9 to opt out."
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors resize-none leading-relaxed"
                      />
                      <p className="text-[10px] text-zinc-600 mt-1">Powered by Kokoro TTS v0.19</p>
                    </div>
                    <div>
                      <Label>Voice</Label>
                      <div className="relative">
                        <select
                          value={(sideData.tts_voice as string) || 'af_heart'}
                          onChange={e => updateNode('tts_voice', e.target.value)}
                          className="w-full appearance-none bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors pr-8"
                        >
                          {TTS_VOICES.map(v => (
                            <option key={v.value} value={v.value} className="bg-zinc-900">
                              {v.label}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                      </div>
                    </div>
                  </>
                )}

                {/* ── Audio File panel ── */}
                {sideData.prompt_type === 'audio' && (
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <Label>Select Audio File</Label>
                      {!!sideData.prompt_audio_id && (
                        <button 
                          onClick={async () => {
                            if (playingTTS) {
                              audioPreviewRef.current?.pause();
                              setPlayingTTS(false);
                              return;
                            }
                            setPlayingTTS(true);
                            try {
                              if (audioPreviewRef.current) {
                                audioPreviewRef.current.src = `/api/v1/audio/${sideData.prompt_audio_id}/stream`;
                                await audioPreviewRef.current.play();
                              }
                            } catch (e) {
                              console.error(e);
                              setPlayingTTS(false);
                            }
                          }}
                          className={`text-xs px-2.5 py-1 rounded-md mb-1 font-medium flex items-center gap-1.5 transition-colors absolute right-6 ${
                            playingTTS 
                              ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' 
                              : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30'
                          }`}
                        >
                          {playingTTS ? <Square className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                          {playingTTS ? "Stop" : "Audition Audio"}
                        </button>
                      )}
                    </div>
                    {audioLoading ? (
                      <div className="flex items-center gap-2 text-zinc-500 text-sm py-2">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading library…
                      </div>
                    ) : audioFiles.length === 0 ? (
                      <div className="text-xs text-zinc-500 bg-white/3 border border-white/8 rounded-lg px-3 py-4 text-center">
                        No audio files uploaded yet.{' '}
                        <Link href="/audio" className="text-blue-400 hover:underline">
                          Upload in Audio Library →
                        </Link>
                      </div>
                    ) : (
                      <div className="relative">
                        <select
                          value={(sideData.prompt_audio_id as string) || ''}
                          onChange={e => {
                            const file = audioFiles.find(f => f.id === e.target.value);
                            if (!selectedNode) return;
                            const updated = {
                              ...selectedNode,
                              data: {
                                ...selectedNode.data,
                                prompt_audio_id: e.target.value || null,
                                prompt_audio_name: file?.name || null
                              }
                            };
                            setNodes(nds => nds.map(n => (n.id === selectedNode.id ? updated : n)));
                            setSelectedNode(updated);
                          }}
                          className="w-full appearance-none bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors pr-8"
                        >
                          <option value="" className="bg-zinc-900">-- Select file --</option>
                          {audioFiles.map(f => (
                            <option key={f.id} value={f.id} className="bg-zinc-900">
                              {f.name} ({f.original_name})
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="w-3.5 h-3.5 text-zinc-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                      </div>
                    )}
                  </div>
                )}

                {sideData.node_type !== 'PROMPT' && (
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 mt-2 mb-4">
                    <p className="text-sm font-medium text-white mb-2">Terminal Node</p>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      This node cannot prompt for inputs or collect keys. It will instantly execute its action ({sideData.node_type as string}) and terminate context when reached.
                    </p>
                  </div>
                )}

                {/* ── Entry point toggle ── */}
                {sideData.node_type === 'PROMPT' && (
                <div className="pt-2 border-t border-white/8">
                  <label className="flex items-center justify-between cursor-pointer">
                    <div>
                      <p className="text-sm font-medium text-white">Call Entry Point</p>
                      <p className="text-[11px] text-zinc-500 mt-0.5">This node plays first when a human answers.</p>
                    </div>
                    <button
                      onClick={() => updateNode('is_start_node', !sideData.is_start_node)}
                      className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${
                        sideData.is_start_node ? 'bg-emerald-500' : 'bg-white/15'
                      }`}
                    >
                      <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                        sideData.is_start_node ? 'translate-x-5' : 'translate-x-0'
                      }`} />
                    </button>
                  </label>
                </div>
                )}
              </>
            )}

            {/* ── EDGE (ROUTE) PROPERTIES ── */}
            {selectedEdge && (
              <>
                <div>
                  <Label>Key Pressed (DTMF)</Label>
                  <input
                    type="text"
                    maxLength={2}
                    value={(selectedEdge.label as string) || ''}
                    onChange={e => updateEdge('label', e.target.value)}
                    placeholder="e.g. 1"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-3xl font-mono text-center text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">The digit the caller must press to take this route.</p>
                </div>
              </>
            )}

            {/* ── Empty state ── */}
            {!selectedNode && !selectedEdge && (
              <div className="text-center mt-16 px-4">
                <GitBranch className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
                <p className="text-sm text-zinc-500">Click a node or a connection line to configure it.</p>
              </div>
            )}
          </div>

          {/* Hidden audio element for previewing */}
          <audio 
            ref={audioPreviewRef} 
            onEnded={() => setPlayingTTS(false)}
            className="hidden" 
          />

          {/* Sidebar footer hint */}
          <div className="px-5 py-3 border-t border-white/8 flex-shrink-0">
            <p className="text-[10px] text-zinc-600 leading-relaxed">
              <strong className="text-zinc-500">Tip:</strong> Drag from the bottom handle of a node to the top handle of another to create a route. Click the line to configure the key and action.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { UploadCloud, Play, Trash2, Music, Pause, Loader2 } from "lucide-react";
import { useState, useEffect, useRef } from "react";

interface AudioFile {
  id: string;
  name: string;
  original_name: string;
  mime_type: string;
  file_size: number;
  created_at: string;
}

export default function AudioLibraryPage() {
  const [isPlaying, setIsPlaying] = useState<string | null>(null);
  const [audioList, setAudioList] = useState<AudioFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

  const fetchAudio = async () => {
    try {
      const res = await fetch(`${API_BASE}/audio/`);
      if (res.ok) {
        setAudioList(await res.json());
      }
    } catch (err) {
      console.error("Failed to fetch audio", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAudio();
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", file.name);

    try {
      const res = await fetch(`${API_BASE}/audio/upload`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        await fetchAudio();
      } else {
        alert("Upload failed.");
      }
    } catch (err) {
      console.error(err);
      alert("Error uploading file.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this audio file?")) return;

    if (isPlaying === id) handleStop();

    try {
      const res = await fetch(`${API_BASE}/audio/${id}`, { method: "DELETE" });
      if (res.ok) {
        setAudioList(prev => prev.filter(a => a.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const togglePlay = (id: string) => {
    if (isPlaying === id) {
      handleStop();
    } else {
      if (audioRef.current) {
        audioRef.current.src = `${API_BASE}/audio/${id}/stream`;
        audioRef.current.play();
        setIsPlaying(id);
      }
    }
  };

  const handleStop = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlaying(null);
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-[1400px] mx-auto relative z-10">
      <audio 
        ref={audioRef} 
        onEnded={handleStop}
        className="hidden" 
      />

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-10 gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">Audio Library</h1>
          <p className="text-muted-foreground w-11/12">Central repository for all static media. Upload 8kHz WAV files for absolute highest SIP routing fidelity.</p>
        </div>
        
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleUpload} 
          accept="audio/*" 
          className="hidden" 
        />
        
        <button 
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="bg-emerald-500 text-black hover:bg-emerald-400 px-6 py-3 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(16,185,129,0.2)] shrink-0 disabled:opacity-50 disabled:active:scale-100 disabled:hover:bg-emerald-500"
        >
          {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <UploadCloud className="w-5 h-5" />}
          {uploading ? "Uploading..." : "Upload New Media"}
        </button>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead>
              <tr className="border-b border-white/10 bg-black/20 text-muted-foreground text-xs uppercase tracking-wider font-semibold">
                <th className="p-4 pl-6">Playback</th>
                <th className="p-4">File Name</th>
                <th className="p-4">Audio Spec</th>
                <th className="p-4">File Size</th>
                <th className="p-4">Uploaded</th>
                <th className="p-4 text-right pr-6">Manage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center text-muted-foreground">
                    <Loader2 className="w-8 h-8 animate-spin mx-auto opacity-50" />
                  </td>
                </tr>
              ) : audioList.map((audio) => (
                <tr key={audio.id} className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                  <td className="p-4 pl-6 w-16">
                     <button 
                        onClick={() => togglePlay(audio.id)}
                        className={`w-10 h-10 rounded-full flex items-center justify-center transition-all shadow-md
                          ${isPlaying === audio.id ? 'bg-emerald-500 text-black shadow-[0_0_15px_rgba(16,185,129,0.4)]' : 'bg-white/10 text-white hover:bg-white/20'}`}
                     >
                        {isPlaying === audio.id ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                     </button>
                  </td>
                  <td className="p-4 font-medium text-white flex items-center gap-3">
                     <Music className="w-4 h-4 text-white/30" />
                     {audio.name}
                  </td>
                  <td className="p-4 text-muted-foreground text-xs font-mono bg-white/5 rounded my-3 inline-block px-2 py-1 tracking-tight">
                    {audio.mime_type.split('/')[1]?.toUpperCase() || 'AUDIO'}
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {(audio.file_size / 1024).toFixed(1)} KB
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {new Date(audio.created_at).toLocaleDateString()}
                  </td>
                  <td className="p-4 text-right pr-6">
                    <button 
                      onClick={(e) => handleDelete(audio.id, e)}
                      className="p-2 rounded-lg text-white/40 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && audioList.length === 0 && (
                 <tr>
                   <td colSpan={6} className="p-12 text-center text-muted-foreground">
                      No audio sequences found in library.
                   </td>
                 </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

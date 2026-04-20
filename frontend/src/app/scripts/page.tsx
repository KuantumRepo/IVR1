"use client";

import { useState, useEffect } from "react";
import ScriptsClient from "./ScriptsClient";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

export default function ScriptsPage() {
  const [scripts, setScripts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadScripts() {
      try {
        const res = await fetch(`${API_BASE}/call-scripts/`);
        if (res.ok) {
          const data = await res.json();
          setScripts(data);
        }
      } catch {
        // silently fail — empty list shown
      } finally {
        setLoading(false);
      }
    }
    loadScripts();
  }, []);

  if (loading) {
    return (
      <div className="p-8 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
        <div className="flex items-center justify-center py-20">
          <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return <ScriptsClient initialScripts={scripts} />;
}

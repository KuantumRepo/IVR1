"use client";

import { useState } from "react";
import { UploadCloud, CheckCircle2, ArrowRight, ArrowLeft, ClipboardPaste, FileSpreadsheet, AlertCircle } from "lucide-react";
import Papa from "papaparse";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

export default function ImportWizard() {
  const router = useRouter();
  
  // ── Active tab ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<"csv" | "paste">("csv");
  
  // ── CSV State ───────────────────────────────────────────────────────────
  const [file, setFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvData, setCsvData] = useState<any[]>([]);
  const [mapping, setMapping] = useState({
     phone_number: "",
     first_name: "",
     last_name: ""
  });

  // ── Paste State ─────────────────────────────────────────────────────────
  const [pasteText, setPasteText] = useState("");
  const [pasteName, setPasteName] = useState("");

  // ── Shared State ────────────────────────────────────────────────────────
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<{
    imported: number;
    skipped_duplicate: number;
    skipped_invalid: number;
    total: number;
  } | null>(null);

  // ── Paste number count ──────────────────────────────────────────────────
  const pasteCount = pasteText.trim()
    ? pasteText.trim().split(/[\n,;\t]+/).filter(n => n.trim()).length
    : 0;

  // ── CSV File Handler ────────────────────────────────────────────────────
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
     const selected = e.target.files?.[0];
     if (selected) {
        setFile(selected);
        setImportResult(null);
        Papa.parse(selected, {
           header: true,
           preview: 5,
           complete: (results) => {
               if (results.meta.fields) setCsvHeaders(results.meta.fields);
               setCsvData(results.data);
               
               // Auto-detect phone column using smart fuzzy matching
               const fields = results.meta.fields || [];
               const phoneCol = fields.find(f => 
                 /phone|cell|mobile|number|tel|dial/i.test(f)
               );
               const firstNameCol = fields.find(f => 
                 /first.?name|fname|given/i.test(f)
               );
               const lastNameCol = fields.find(f => 
                 /last.?name|lname|surname|family/i.test(f)
               );
               
               setMapping({
                 phone_number: phoneCol || "",
                 first_name: firstNameCol || "",
                 last_name: lastNameCol || "",
               });
           }
        });
     }
  };

  // ── CSV Import Handler ──────────────────────────────────────────────────
  const handleCSVImport = async () => {
      if (!file || !mapping.phone_number) return;
      setIsImporting(true);
      setImportResult(null);
      try {
          // 1. Create the container list
          const listRes = await fetch(`${API_URL}/contact-lists/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: file.name.replace(/\.[^/.]+$/, "") })
          });
          if (!listRes.ok) throw new Error("List creation failed");
          const listData = await listRes.json();
          
          // 2. Upload CSV with column mapping as query params
          const params = new URLSearchParams({
            phone_col: mapping.phone_number,
            ...(mapping.first_name && { first_name_col: mapping.first_name }),
            ...(mapping.last_name && { last_name_col: mapping.last_name }),
          });
          
          const formData = new FormData();
          formData.append("file", file);
          const uploadRes = await fetch(
            `${API_URL}/contact-lists/${listData.id}/upload-csv?${params.toString()}`,
            { method: 'POST', body: formData }
          );
          if (!uploadRes.ok) {
            const err = await uploadRes.json().catch(() => ({}));
            throw new Error(err.detail || "Upload failed");
          }
          
          const result = await uploadRes.json();
          setImportResult({
            imported: result.imported,
            skipped_duplicate: result.skipped_duplicate,
            skipped_invalid: result.skipped_invalid,
            total: result.total_in_file,
          });
          
      } catch (err: any) {
          console.error("CSV import error", err);
          alert(err.message || "Import failed. Check CSV format.");
      } finally {
          setIsImporting(false);
      }
  };

  // ── Paste Import Handler ────────────────────────────────────────────────
  const handlePasteImport = async () => {
      if (!pasteText.trim()) return;
      setIsImporting(true);
      setImportResult(null);
      try {
          const res = await fetch(`${API_URL}/contact-lists/quick-import`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  numbers: pasteText,
                  list_name: pasteName || `Paste Import ${new Date().toLocaleDateString()}`,
              }),
          });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Import failed");
          }
          
          const result = await res.json();
          setImportResult({
            imported: result.imported,
            skipped_duplicate: result.skipped_duplicate,
            skipped_invalid: result.skipped_invalid,
            total: result.total_submitted,
          });
      } catch (err: any) {
          console.error("Paste import error", err);
          alert(err.message || "Import failed.");
      } finally {
          setIsImporting(false);
      }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-4xl mx-auto relative z-10">
      
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-2">
          <Link href="/contacts" className="text-muted-foreground hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Import Contacts</h1>
        </div>
        <p className="text-muted-foreground ml-8">Upload a CSV file or paste phone numbers directly to create a contact list.</p>
      </div>

      {/* ── Import Results Banner ──────────────────────────────────────────── */}
      {importResult && (
        <div className="mb-8 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl p-6 animate-in fade-in slide-in-from-top-4 shadow-[0_0_30px_rgba(16,185,129,0.1)]">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-white mb-3">Import Complete</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-emerald-500/10 rounded-xl p-4 text-center border border-emerald-500/10">
                  <div className="text-2xl font-bold text-emerald-400">{importResult.imported}</div>
                  <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">Imported</div>
                </div>
                <div className="bg-amber-500/5 rounded-xl p-4 text-center border border-amber-500/10">
                  <div className="text-2xl font-bold text-amber-400">{importResult.skipped_duplicate}</div>
                  <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">Duplicates Skipped</div>
                </div>
                <div className="bg-red-500/5 rounded-xl p-4 text-center border border-red-500/10">
                  <div className="text-2xl font-bold text-red-400">{importResult.skipped_invalid}</div>
                  <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">Invalid Skipped</div>
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <Link
                  href="/contacts"
                  className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 text-sm"
                >
                  View Contact Lists →
                </Link>
                <button
                  onClick={() => { setImportResult(null); setFile(null); setPasteText(""); }}
                  className="px-5 py-2.5 rounded-lg font-medium text-white border border-white/10 hover:bg-white/5 transition-colors text-sm"
                >
                  Import More
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Method Tabs ───────────────────────────────────────────────────── */}
      {!importResult && (
        <>
          <div className="flex gap-1 mb-6 bg-white/5 p-1 rounded-xl border border-white/10 w-fit">
            <button
              onClick={() => setActiveTab("csv")}
              className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === "csv"
                  ? "bg-white text-black shadow-lg"
                  : "text-muted-foreground hover:text-white hover:bg-white/5"
              }`}
            >
              <FileSpreadsheet className="w-4 h-4" /> Upload CSV
            </button>
            <button
              onClick={() => setActiveTab("paste")}
              className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === "paste"
                  ? "bg-white text-black shadow-lg"
                  : "text-muted-foreground hover:text-white hover:bg-white/5"
              }`}
            >
              <ClipboardPaste className="w-4 h-4" /> Paste Numbers
            </button>
          </div>

          {/* ═══════════════════════════════════════════════════════════════════
              TAB 1: CSV Upload
           ═══════════════════════════════════════════════════════════════════ */}
          {activeTab === "csv" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-200">
              {!file ? (
                <div className="border border-dashed border-white/20 rounded-2xl bg-white/5 p-16 text-center hover:bg-white/10 transition-colors cursor-pointer relative group">
                   <input type="file" accept=".csv" onChange={handleFileUpload} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                   <UploadCloud className="w-12 h-12 text-white/30 mx-auto mb-4 group-hover:text-emerald-400 group-hover:scale-110 transition-all duration-300" />
                   <h3 className="text-lg font-medium text-white mb-2 tracking-tight">Drop CSV file here or click to browse</h3>
                   <p className="text-muted-foreground text-sm max-w-sm mx-auto">Supports any CSV format — map your columns in the next step.</p>
                </div>
              ) : (
                <div className="space-y-6">
                   {/* Selected File Banner */}
                   <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex items-center justify-between shadow-[0_0_20px_rgba(16,185,129,0.1)]">
                      <div className="flex items-center gap-3">
                         <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                         <div>
                            <div className="text-white font-medium">{file.name}</div>
                            <div className="text-xs text-muted-foreground mt-0.5">{(file.size / 1024).toFixed(1)} KB · {csvHeaders.length} columns detected</div>
                         </div>
                      </div>
                      <button onClick={() => { setFile(null); setCsvHeaders([]); setCsvData([]); }} className="text-sm font-medium text-muted-foreground hover:text-white transition-colors">Remove</button>
                   </div>

                   {/* Column Mapping */}
                   <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
                      <h3 className="text-lg font-medium text-white mb-6">Map Your Columns</h3>
                      
                      <div className="grid grid-cols-[1fr,40px,1fr] gap-5 items-center">
                         <div className="text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">System Field</div>
                         <div></div>
                         <div className="text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">Your CSV Column</div>

                         {/* Phone Mapping (required) */}
                         <div className="bg-white/5 py-3.5 px-4 rounded-lg text-white font-medium border border-emerald-500/20 shadow-inner">
                            Phone Number <span className="text-red-400 inline-block ml-1">*</span>
                         </div>
                         <div className="flex justify-center"><ArrowRight className="w-4 h-4 text-emerald-500/50" /></div>
                         <select 
                            value={mapping.phone_number} onChange={(e) => setMapping({...mapping, phone_number: e.target.value})}
                            className="w-full bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-4 py-3.5 text-emerald-400 font-medium focus:outline-none transition-colors appearance-none shadow-[0_0_20px_rgba(16,185,129,0.15)]"
                         >
                            <option value="">-- Select Column --</option>
                            {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                         </select>

                         {/* First Name */}
                         <div className="bg-white/5 py-3.5 px-4 rounded-lg text-white font-medium border border-white/10 shadow-inner mt-2">
                            First Name
                         </div>
                         <div className="flex justify-center mt-2"><ArrowRight className="w-4 h-4 text-white/20" /></div>
                         <select 
                            value={mapping.first_name} onChange={(e) => setMapping({...mapping, first_name: e.target.value})}
                            className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3.5 text-white mt-2 focus:outline-none focus:border-white/30 transition-colors appearance-none"
                         >
                            <option value="">-- Skip --</option>
                            {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                         </select>

                         {/* Last Name */}
                         <div className="bg-white/5 py-3.5 px-4 rounded-lg text-white font-medium border border-white/10 shadow-inner mt-2">
                            Last Name
                         </div>
                         <div className="flex justify-center mt-2"><ArrowRight className="w-4 h-4 text-white/20" /></div>
                         <select 
                            value={mapping.last_name} onChange={(e) => setMapping({...mapping, last_name: e.target.value})}
                            className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3.5 text-white mt-2 focus:outline-none focus:border-white/30 transition-colors appearance-none"
                         >
                            <option value="">-- Skip --</option>
                            {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                         </select>
                      </div>

                      {!mapping.phone_number && (
                        <div className="flex items-center gap-2 mt-4 text-amber-400/80">
                          <AlertCircle className="w-4 h-4" />
                          <span className="text-sm">Select which column contains phone numbers to continue.</span>
                        </div>
                      )}
                   </div>

                   {/* CSV Preview */}
                   {csvData.length > 0 && (
                      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-xl">
                          <div className="bg-white/5 px-6 py-4 border-b border-white/5 flex gap-2 items-center">
                             <h4 className="text-sm font-medium text-white tracking-tight">Data Preview</h4>
                             <span className="bg-white/10 text-muted-foreground text-[10px] px-2 py-0.5 rounded font-mono uppercase">First 5 rows</span>
                          </div>
                          <div className="overflow-x-auto">
                             <table className="w-full text-left text-sm whitespace-nowrap">
                                <thead>
                                   <tr className="border-b border-white/5">
                                     {csvHeaders.map(h => (
                                       <th key={h} className={`p-4 font-semibold text-xs tracking-wider uppercase ${
                                         h === mapping.phone_number 
                                           ? 'text-emerald-400 bg-emerald-500/5'
                                           : h === mapping.first_name || h === mapping.last_name
                                             ? 'text-blue-400 bg-blue-500/5'
                                             : 'text-muted-foreground bg-black/20'
                                       }`}>{h}</th>
                                     ))}
                                   </tr>
                                </thead>
                                <tbody>
                                   {csvData.map((row, i) => (
                                      <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                         {csvHeaders.map(h => (
                                           <td key={h} className={`p-4 font-mono text-xs ${
                                             h === mapping.phone_number ? 'text-emerald-300' : 'text-neutral-300'
                                           }`}>{row[h]}</td>
                                         ))}
                                      </tr>
                                   ))}
                                </tbody>
                             </table>
                          </div>
                      </div>
                   )}

                   {/* Import Button */}
                   <div className="flex justify-end pt-4 border-t border-white/10">
                      <button 
                        onClick={handleCSVImport}
                        disabled={!mapping.phone_number || isImporting}
                        className={`px-8 py-3.5 rounded-lg font-medium transition-all shadow-xl flex items-center gap-3 tracking-tight
                           ${!mapping.phone_number ? 'bg-white/10 text-white/30 cursor-not-allowed' : 'bg-emerald-500 text-black hover:bg-emerald-400 active:scale-95 shadow-[0_0_30px_rgba(16,185,129,0.3)]'}`}
                      >
                        {isImporting ? 'Importing...' : 'Import Contacts'} <ArrowRight className="w-4 h-4" />
                      </button>
                   </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════
              TAB 2: Paste Numbers
           ═══════════════════════════════════════════════════════════════════ */}
          {activeTab === "paste" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-left-4 duration-200">
              <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
                
                <h3 className="text-lg font-medium text-white mb-1">Quick Paste</h3>
                <p className="text-sm text-muted-foreground mb-6">Paste phone numbers from a spreadsheet, one per line. Commas, semicolons, and tabs are also supported as separators.</p>

                {/* List Name */}
                <div className="mb-5">
                  <label className="text-sm font-medium text-white mb-2 block">List Name</label>
                  <input 
                    type="text" 
                    value={pasteName}
                    onChange={(e) => setPasteName(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-white/30 transition-colors"
                    placeholder="e.g. Solar Leads March 2026"
                  />
                </div>

                {/* Textarea */}
                <div className="relative">
                  <textarea
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-4 text-white font-mono text-sm focus:outline-none focus:border-emerald-500/30 transition-colors h-64 resize-none"
                    placeholder={"5551234567\n5559876543\n(555) 123-4567\n+1-555-987-6543\n..."}
                  />
                  {/* Live counter */}
                  {pasteCount > 0 && (
                    <div className="absolute bottom-3 right-3 bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded-full text-xs font-bold border border-emerald-500/20">
                      {pasteCount} numbers detected
                    </div>
                  )}
                </div>

                <p className="text-xs text-muted-foreground mt-3">
                  All numbers are validated and normalized to E.164 format using Google's libphonenumber. Invalid numbers are automatically skipped.
                </p>
              </div>

              {/* Import Button */}
              <div className="flex justify-end pt-4 border-t border-white/10">
                <button
                  onClick={handlePasteImport}
                  disabled={pasteCount === 0 || isImporting}
                  className={`px-8 py-3.5 rounded-lg font-medium transition-all shadow-xl flex items-center gap-3 tracking-tight
                     ${pasteCount === 0 ? 'bg-white/10 text-white/30 cursor-not-allowed' : 'bg-emerald-500 text-black hover:bg-emerald-400 active:scale-95 shadow-[0_0_30px_rgba(16,185,129,0.3)]'}`}
                >
                  {isImporting ? 'Importing...' : `Import ${pasteCount} Numbers`} <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

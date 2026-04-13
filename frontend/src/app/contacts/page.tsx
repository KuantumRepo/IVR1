"use client";

import { useState, useEffect } from "react";
import { Contact2, UploadCloud, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

interface ContactList {
  id: string;
  name: string;
  description: string | null;
  total_contacts: number;
  created_at: string;
}

interface ContactRow {
  id: string;
  phone_number: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  created_at: string | null;
}

export default function ContactsPage() {
  const router = useRouter();
  const [lists, setLists] = useState<ContactList[]>([]);
  const [expandedListId, setExpandedListId] = useState<string | null>(null);
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const [contactsTotal, setContactsTotal] = useState(0);
  const [contactsLoading, setContactsLoading] = useState(false);

  const fetchLists = async () => {
    try {
      const res = await fetch(`${API_URL}/contact-lists/`);
      if (res.ok) setLists(await res.json());
    } catch (err) {
      console.error("Failed to fetch lists", err);
    }
  };

  useEffect(() => { fetchLists(); }, []);

  const handleExpand = async (listId: string) => {
    if (expandedListId === listId) {
      setExpandedListId(null);
      setContacts([]);
      return;
    }

    setExpandedListId(listId);
    setContactsLoading(true);
    try {
      const res = await fetch(`${API_URL}/contact-lists/${listId}/contacts?per_page=50`);
      if (res.ok) {
        const data = await res.json();
        setContacts(data.contacts || []);
        setContactsTotal(data.total || 0);
      }
    } catch (err) {
      console.error("Failed to fetch contacts", err);
    } finally {
      setContactsLoading(false);
    }
  };

  const handleDelete = async (listId: string) => {
    if (!confirm("Are you sure you want to delete this list and all its contacts?")) return;
    try {
      const res = await fetch(`${API_URL}/contact-lists/${listId}`, { method: 'DELETE' });
      if (res.ok) {
        setLists(prev => prev.filter(l => l.id !== listId));
        if (expandedListId === listId) {
          setExpandedListId(null);
          setContacts([]);
        }
      } else {
        alert("Failed to delete list");
      }
    } catch (e) {
      alert("Failed to delete list");
    }
  };

  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Contact Lists</h1>
          <p className="text-muted-foreground">Manage leads and import contacts via CSV or paste.</p>
        </div>
        <Link href="/contacts/import" className="bg-white text-black hover:bg-neutral-200 px-5 py-2.5 rounded-lg font-medium transition-transform active:scale-95 flex items-center gap-2 shadow-[0_0_20px_rgba(255,255,255,0.2)]">
          <UploadCloud className="w-4 h-4" />
          Import Contacts
        </Link>
      </div>

      <div className="bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              <th className="font-medium text-muted-foreground p-4 w-8"></th>
              <th className="font-medium text-muted-foreground p-4">List Name</th>
              <th className="font-medium text-muted-foreground p-4">Description</th>
              <th className="font-medium text-muted-foreground p-4">Contacts</th>
              <th className="font-medium text-muted-foreground p-4">Created</th>
              <th className="font-medium text-muted-foreground p-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {lists.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-12 text-center text-muted-foreground">
                  <Contact2 className="w-8 h-8 opacity-50 mx-auto mb-3" />
                  No contact lists yet. Import contacts to get started.
                </td>
              </tr>
            ) : (
              lists.map((list) => (
                <>
                  <tr 
                    key={list.id} 
                    className="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer"
                    onClick={() => handleExpand(list.id)}
                  >
                    <td className="p-4 text-muted-foreground">
                      {expandedListId === list.id 
                        ? <ChevronDown className="w-4 h-4 text-emerald-400" /> 
                        : <ChevronRight className="w-4 h-4" />
                      }
                    </td>
                    <td className="p-4 font-medium text-white">{list.name}</td>
                    <td className="p-4 text-muted-foreground">{list.description || '—'}</td>
                    <td className="p-4">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border bg-blue-500/10 text-blue-400 border-blue-500/20">
                        {list.total_contacts.toLocaleString()}
                      </span>
                    </td>
                    <td className="p-4 text-muted-foreground">{new Date(list.created_at).toLocaleDateString()}</td>
                    <td className="p-4 text-right">
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleDelete(list.id); }} 
                        className="p-2 rounded-lg bg-destructive/10 text-destructive-foreground hover:bg-destructive/20 transition-colors"
                        title="Delete list"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                  
                  {/* Expanded Contact Sub-table */}
                  {expandedListId === list.id && (
                    <tr key={`${list.id}-expanded`}>
                      <td colSpan={6} className="p-0">
                        <div className="bg-white/[0.02] border-y border-white/5 animate-in fade-in slide-in-from-top-2 duration-200">
                          {contactsLoading ? (
                            <div className="p-8 text-center text-muted-foreground text-sm">Loading contacts...</div>
                          ) : contacts.length === 0 ? (
                            <div className="p-8 text-center text-muted-foreground text-sm">No contacts in this list.</div>
                          ) : (
                            <>
                              <table className="w-full text-left">
                                <thead>
                                  <tr className="border-b border-white/5">
                                    <th className="py-2.5 px-6 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Phone</th>
                                    <th className="py-2.5 px-4 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">First Name</th>
                                    <th className="py-2.5 px-4 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Last Name</th>
                                    <th className="py-2.5 px-4 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Email</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {contacts.map((c) => (
                                    <tr key={c.id} className="border-b border-white/[0.03] hover:bg-white/[0.03] transition-colors">
                                      <td className="py-2 px-6 font-mono text-xs text-emerald-400">{c.phone_number}</td>
                                      <td className="py-2 px-4 text-xs text-neutral-300">{c.first_name || '—'}</td>
                                      <td className="py-2 px-4 text-xs text-neutral-300">{c.last_name || '—'}</td>
                                      <td className="py-2 px-4 text-xs text-neutral-300">{c.email || '—'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {contactsTotal > 50 && (
                                <div className="px-6 py-3 text-xs text-muted-foreground border-t border-white/5 bg-black/10">
                                  Showing 50 of {contactsTotal.toLocaleString()} contacts
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

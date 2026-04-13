"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  LayoutDashboard, 
  PhoneCall, 
  Users, 
  Contact2, 
  CassetteTape,
  Music,
  UserCircle,
  Settings2,
  Activity,
  BarChart3
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Campaigns", href: "/campaigns", icon: Activity },
    { name: "Audio Files", href: "/audio", icon: Music },
    { name: "Call Scripts", href: "/scripts", icon: CassetteTape },
    { name: "Contact Lists", href: "/contacts", icon: Contact2 },
    { name: "Agents", href: "/agents", icon: Users },
    { name: "Caller IDs", href: "/caller-ids", icon: UserCircle },
    { name: "SIP Trunks", href: "/gateways", icon: PhoneCall },
    { name: "Analytics", href: "/analytics", icon: BarChart3 },
    { name: "Settings", href: "/settings", icon: Settings2 },
  ];

  return (
    <div className="w-64 border-r border-white/5 bg-background/40 backdrop-blur-3xl flex flex-col h-full shrink-0 relative z-10 transition-all duration-300">
      <div className="p-6 flex items-center gap-3 border-b border-white/5">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-white to-white/60 flex items-center justify-center shadow-[0_0_15px_rgba(255,255,255,0.4)]">
          <PhoneCall className="w-5 h-5 text-black" />
        </div>
        <h1 className="font-semibold text-lg tracking-tight select-none">Broadcaster</h1>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        <div className="mb-4 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/60">
          Core Engine
        </div>
        
        {links.map((link) => {
          const isActive = pathname === link.href;
          const Icon = link.icon;
          
          return (
            <Link
              key={link.name}
              href={link.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group relative ${
                isActive 
                  ? "bg-white/10 text-white font-medium" 
                  : "text-muted-foreground hover:bg-white/5 hover:text-white"
              }`}
            >
              {isActive && (
                <div className="absolute left-0 w-1 h-5 bg-white rounded-r-full animate-in fade-in zoom-in" />
              )}
              <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-muted-foreground group-hover:text-white"}`} />
              {link.name}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/5">
        <div className="rounded-xl bg-background/60 backdrop-blur-xl border border-white/10 p-4 flex flex-col gap-2 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-10">
            <Activity className="w-16 h-16" />
          </div>
          <p className="text-xs text-muted-foreground font-medium z-10">Engine Status</p>
          <div className="flex items-center gap-2 z-10">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-sm font-medium text-emerald-400">Online & Routing</span>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { WebSocketProvider } from "@/providers/WebSocketProvider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";

  // Login page renders standalone — no sidebar, no WebSocket
  if (isLoginPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <WebSocketProvider>
        <Sidebar />
        <main className="flex-1 flex flex-col relative overflow-y-auto">
          {children}
        </main>
      </WebSocketProvider>
    </div>
  );
}

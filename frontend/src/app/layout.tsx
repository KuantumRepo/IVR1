import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { WebSocketProvider } from "@/providers/WebSocketProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Broadcaster Admin",
  description: "Premium Voice Broadcasting & Agent Transfer Engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} dark-mesh min-h-screen text-foreground`}>
        <div className="flex h-screen overflow-hidden">
          <WebSocketProvider>
            <Sidebar />
            <main className="flex-1 flex flex-col relative overflow-y-auto">
              {children}
            </main>
          </WebSocketProvider>
        </div>
      </body>
    </html>
  );
}

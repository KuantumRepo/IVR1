import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Login — Broadcaster",
  description: "System access authentication",
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Login page has its own standalone layout — no sidebar, no nav, no app shell
  return <>{children}</>;
}

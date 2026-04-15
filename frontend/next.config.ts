import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  output: "standalone",
  // API routing handled by Caddy reverse proxy (prod) or docker-compose.override (dev).
  // Do NOT add rewrites to 127.0.0.1 — they break in standalone Docker builds.
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // lean, self-contained server bundle for Docker
  output: "standalone",
  async rewrites() {
    const backend = process.env.PULSE_BACKEND_URL || "http://127.0.0.1:8787";
    return [
      { source: "/api/:path*", destination: `${backend}/:path*` },
    ];
  },
};

export default nextConfig;

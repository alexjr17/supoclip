import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  // Skip ESLint during builds (generated Prisma code causes lint errors)
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Skip TypeScript errors during builds for now
  typescript: {
    ignoreBuildErrors: false,
  },
  // Remotion's bundler and renderer ship native .node binaries (rspack bindings,
  // the headless browser launcher) that webpack cannot parse. They are required
  // at runtime from node_modules instead of being bundled.
  serverExternalPackages: [
    "@remotion/bundler",
    "@remotion/renderer",
  ],
  async rewrites() {
    return [
      {
        source: "/js/script.js",
        destination: "https://datafa.st/js/script.js",
      },
      {
        source: "/api/events",
        destination: "https://datafa.st/api/events",
      },
    ];
  },
};

export default nextConfig;

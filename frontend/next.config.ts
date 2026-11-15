import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server (server.js + only the node_modules it needs): this is what the
  // Docker image runs, so the image does not carry the whole development tree.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

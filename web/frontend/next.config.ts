import type { NextConfig } from "next";
import path from "node:path";

// Contracts are shared with the separate backend and live beside frontend/.
const projectRoot = path.resolve(__dirname, "..");
const config: NextConfig = {
  poweredByHeader: false,
  turbopack: { root: projectRoot },
  outputFileTracingRoot: projectRoot,
};
export default config;

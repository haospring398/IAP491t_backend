import type { ProxyConfig } from "./proxy";
// Pure selection/validation permits hermetic tests without importing server-only.
export function resolveBackendConfig(raw?: string, token?: string): ProxyConfig {
  if (!raw || !token || /[\u0000-\u0020\u007f-\uffff]/.test(token)) return null;
  try {
    const url = new URL(raw);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if ((url.protocol !== "https:" && !(url.protocol === "http:" && local)) || url.username || url.password || url.search || url.hash) return null;
    return { url: url.href, token };
  } catch { return null; }
}

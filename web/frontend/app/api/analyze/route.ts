import { analyzeProxy } from "@/lib/proxy";
import { backendConfig } from "@/lib/server-config";
export const runtime = "nodejs";
export async function POST(request: Request) { return analyzeProxy(request, backendConfig()); }

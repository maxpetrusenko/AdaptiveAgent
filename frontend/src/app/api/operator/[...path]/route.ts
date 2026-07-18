import { NextRequest, NextResponse } from "next/server";

import {
  assertLocalProxyRequest,
  LocalProxyAccessError,
} from "@/lib/local-proxy-policy";
import { buildOperatorBackendUrl } from "@/lib/operator-proxy";
import { proofProxyHeaders } from "@/lib/proof-proxy";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext) {
  try {
    assertLocalProxyRequest({
      mode: process.env.OPERATOR_PROXY_MODE,
      requestUrl: request.url,
      origin: request.headers.get("origin"),
      fetchSite: request.headers.get("sec-fetch-site"),
      method: request.method,
    });
    const { path } = await context.params;
    const backendUrl = buildOperatorBackendUrl(
      process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000",
      request.method,
      path,
      request.nextUrl.search
    );
    const response = await fetch(backendUrl, {
      method: request.method,
      headers: proofProxyHeaders(
        request.headers,
        process.env.OPERATOR_API_TOKEN
      ),
      body: await request.arrayBuffer(),
      redirect: "manual",
      signal: AbortSignal.timeout(90_000),
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    if (error instanceof LocalProxyAccessError) {
      return NextResponse.json(
        { detail: "Operator proxy unavailable" },
        { status: 403 }
      );
    }
    const message =
      error instanceof Error ? error.message : "Operator proxy request failed";
    const status = /not allowed|invalid/i.test(message) ? 404 : 502;
    return NextResponse.json({ detail: message }, { status });
  }
}

export const DELETE = proxy;
export const POST = proxy;

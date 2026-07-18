export interface LocalProxyRequest {
  mode: string | undefined;
  requestUrl: string;
  origin: string | null;
  fetchSite: string | null;
  method?: string;
}

export class LocalProxyAccessError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocalProxyAccessError";
  }
}

export function assertLocalProxyRequest(request: LocalProxyRequest): void {
  if (request.mode !== "local") {
    throw new LocalProxyAccessError("Local operator proxy is disabled");
  }

  const requestUrl = new URL(request.requestUrl);
  if (!isLoopbackHostname(requestUrl.hostname)) {
    throw new LocalProxyAccessError("Local operator proxy requires a loopback host");
  }
  if (request.fetchSite !== "same-origin") {
    throw new LocalProxyAccessError(
      "Local operator proxy requires a same-origin browser request"
    );
  }

  const method = (request.method || "POST").toUpperCase();
  if (method !== "GET" && !request.origin) {
    throw new LocalProxyAccessError(
      "Local operator mutation requires a same-origin Origin header"
    );
  }
  if (request.origin && request.origin !== requestUrl.origin) {
    throw new LocalProxyAccessError(
      "Local operator proxy requires a same-origin request"
    );
  }
}

function isLoopbackHostname(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]" ||
    hostname === "::1"
  );
}

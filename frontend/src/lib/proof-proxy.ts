const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;

export function buildProofBackendUrl(
  backendBase: string,
  method: string,
  segments: string[],
  search: string
): string {
  if (
    segments.length === 0 ||
    segments.some(
      (segment) =>
        !SAFE_SEGMENT.test(segment) || segment === "." || segment === ".."
    )
  ) {
    throw new Error("Invalid proof proxy path");
  }
  const path = segments.join("/");
  if (!isAllowedProofPath(method, path)) {
    throw new Error("Proof proxy route is not allowed");
  }
  const base = backendBase.replace(/\/+$/, "");
  return `${base}/api/${path}${search}`;
}

export function proofProxyHeaders(
  incoming: Headers,
  operatorToken: string | undefined
): Headers {
  const headers = new Headers();
  const contentType = incoming.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  if (operatorToken) {
    headers.set("x-operator-token", operatorToken);
  }
  return headers;
}

function isAllowedProofPath(method: string, path: string): boolean {
  const normalizedMethod = method.toUpperCase();
  return (
    (normalizedMethod === "GET" && path === "knowledge/index/health") ||
    (normalizedMethod === "POST" && path === "knowledge/ingest") ||
    (normalizedMethod === "POST" && path === "knowledge/search") ||
    (normalizedMethod === "POST" &&
      /^research\/[^/]+\/runs(?:\/[^/]+\/run)?$/.test(path)) ||
    (normalizedMethod === "GET" &&
      /^research\/[^/]+\/runs\/[^/]+$/.test(path))
  );
}

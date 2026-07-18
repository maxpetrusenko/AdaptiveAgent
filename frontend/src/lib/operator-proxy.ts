const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;

export function buildOperatorBackendUrl(
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
    throw new Error("Invalid operator proxy path");
  }

  const path = segments.join("/");
  if (!isAllowedOperatorMutation(method, path)) {
    throw new Error("Operator proxy route is not allowed");
  }

  const base = backendBase.replace(/\/+$/, "");
  return `${base}/api/${path}${search}`;
}

function isAllowedOperatorMutation(method: string, path: string): boolean {
  const normalizedMethod = method.toUpperCase();
  return (
    (normalizedMethod === "POST" &&
      /^tasks\/[^/]+\/(?:pause|resume|cancel)$/.test(path)) ||
    (normalizedMethod === "POST" &&
      /^adapt\/candidates\/[^/]+\/(?:promote|rollback)$/.test(path)) ||
    (normalizedMethod === "POST" && path === "adapt/improve") ||
    (normalizedMethod === "POST" && path === "cases") ||
    (normalizedMethod === "DELETE" && /^cases\/[^/]+$/.test(path)) ||
    (normalizedMethod === "POST" && path === "evals/run")
  );
}

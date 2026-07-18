export function safeArtifactHref(value: string | null): string | null {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") {
      return value;
    }
    if (
      url.protocol === "trace:" &&
      !url.username &&
      !url.password &&
      Boolean(url.hostname)
    ) {
      return value;
    }
  } catch {
    return null;
  }

  return null;
}

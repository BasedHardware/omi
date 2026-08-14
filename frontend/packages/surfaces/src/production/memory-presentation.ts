const PROVENANCE_PREFIX = /^([a-z][a-z0-9_-]{1,80}):\s+([\s\S]+)$/i;

/** Separate legacy provenance from user-facing memory copy without changing storage. */
export function presentMemoryContent(content: string): { provenance: string | null; body: string } {
  const match = PROVENANCE_PREFIX.exec(content);
  return match
    ? { provenance: `${match[1]}:`, body: match[2] ?? "" }
    : { provenance: null, body: content };
}

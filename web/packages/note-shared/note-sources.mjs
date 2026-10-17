/** Only typed provenance resolving to this loaded transcript can become a source chip. */
export function resolvableNoteSources(sourceIDs = [], transcriptIDs = []) {
  const valid = new Set(transcriptIDs.filter(Boolean));
  return [...new Set(sourceIDs)].filter((id) => valid.has(id));
}

export function repairNoteCitations(
  input: string,
  knownIDs?: Iterable<string>
): { text: string; sourceIDs: string[] };

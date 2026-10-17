/** Read-time repair only. Expectations live in contracts/note_citation_contract.json. */
function repairPass(input, knownIDs) {
  const valid = new Set(knownIDs);
  const protectedUnits = new Map();
  let prefix = "\uE000";
  while (input.includes(prefix)) prefix += "\uE000";
  const protect = (value) => {
    const key = `${prefix}${"\uE002".repeat(protectedUnits.size)}\uE001`;
    protectedUnits.set(key, value);
    return key;
  };
  const marker = "\0";
  let text = input.replace(
    /^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^[ \t]{0,3}\1[`~]*[ \t]*(?:\n|$)|(?![\s\S]))|(`+)(?!`)[\s\S]*?(?<!`)\2(?!`)/gm,
    protect
  );
  const recovered = [];
  const remove = (ids = []) => {
    recovered.push(...ids);
    return marker;
  };
  const cleanSeparators = (value) =>
    value
      .replace(/[\0\x01]/g, "")
      .replace(/^[\s,;]+|[\s,;]+$/g, "")
      .replace(/([,;])(?:\s*[,;])+/g, "$1");
  const linkPattern = /^\[([^\]\n]*)\]\(([^)\n]*)\)$/;
  const unit = (value) => {
    const link = value.match(linkPattern);
    if (link) {
      const label = link[1].trim();
      if (!label) return remove();
      if (valid.has(label)) return remove([label]);
      const destination = link[2].trim();
      const scheme = destination.includes(":")
        ? destination.split(":")[0].toLowerCase()
        : "";
      return ["http", "https", "mailto"].includes(scheme)
        ? protect(value)
        : label;
    }
    if (value.startsWith("(")) {
      const ids = value
        .slice(1, -1)
        .split(/[;,]/)
        .map((token) => {
          const nested = token.trim().match(linkPattern);
          return nested ? nested[1].trim() : token.trim();
        })
        .filter(Boolean);
      return ids.length && ids.every((id) => valid.has(id))
        ? remove(ids)
        : value.replace(
            /\[[^\[\]\n]*\]\([^\n)]*\)|[\[［【][^\[\]［］【】\n]*[\]］】]/g,
            unit
          );
    }
    const content = value
      .slice(1, -1)
      .replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, "")
      .trim();
    const tokens = content.split(/[\s,;]+/).filter(Boolean);
    if (tokens.length && tokens.every((id) => valid.has(id)))
      return remove(tokens);
    const header = content.split(/\s+/);
    if (
      header.length === 2 &&
      valid.has(header[0]) &&
      /^[?]?[0-9A-Za-z]{1,3}$/.test(header[1])
    )
      return remove([header[0]]);
    const mixedIDs = tokens.filter((id) => valid.has(id));
    if (mixedIDs.length) {
      recovered.push(...mixedIDs);
      return cleanSeparators(
        content.replace(/[^\s,;]+/g, (token) => (valid.has(token) ? "" : token))
      );
    }
    if (
      !tokens.length ||
      /^(?:spk|speaker)[ _]\d+:?$/i.test(content) ||
      /^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,95}|\^\d+)$/.test(content)
    )
      return remove();
    return protect(value);
  };
  text = text.replace(
    /\[[^\[\]\n]*\]\([^\n)]*\)|(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)|[\[［【][^\[\]［］【】\n]*[\]］】]/g,
    unit
  );
  for (const id of [...valid].sort(
    (a, b) => b.length - a.length || a.localeCompare(b)
  )) {
    const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    text = text.replace(
      new RegExp(`(?<![\\w-])${escaped}(?![\\w-])`, "gu"),
      marker
    );
  }
  text = text.replace(/\b(?:spk|speaker)[ _]\d+\b:?[ \t]*/gi, marker);
  for (;;) {
    const cleaned = text.replace(/\([^()\n]*\)/g, (value) => {
      if (!/[\0\x01]/.test(value)) return value;
      const content = cleanSeparators(value.slice(1, -1));
      return content ? `(${content})` : "\x01";
    });
    if (cleaned === text) break;
    text = cleaned;
  }
  if (text.includes(marker)) {
    text = text
      .replace(/\0(?:[ \t]*\0)+/g, marker)
      .replace(/[ \t]+\0[ \t]+/g, " ")
      .replace(/[ \t]+\0(?=[,.;:]|\n|$)/g, "")
      .replace(/\0[ \t]+/g, "")
      .replace(/\0/g, "")
      .trim();
  }
  if (text.includes("\x01")) text = text.replaceAll("\x01", "").trim();
  for (const [key, value] of [...protectedUnits].reverse())
    text = text.replaceAll(key, value);
  return { text, sourceIDs: [...new Set(recovered)] };
}

export function repairNoteCitations(input, knownIDs = []) {
  const ids = [...knownIDs];
  const recovered = [];
  let text = input;
  for (;;) {
    const result = repairPass(text, ids);
    recovered.push(...result.sourceIDs);
    if (result.text === text)
      return { text, sourceIDs: [...new Set(recovered)] };
    text = result.text;
  }
}

/** Read-time repair only. Expectations live in contracts/note_citation_contract.json. */

const FENCE =
  /^[ \t]{0,3}(`{3,}(?!`)|~{3,}(?!~))[^\n]*\n[\s\S]*?(?:^[ \t]{0,3}\1[`~]*[ \t]*(?:\n|$)|(?![\s\S]))/my;

/**
 * Replace fenced blocks and inline code spans through `protect`, left to right.
 * Same matches as the former single regex
 * `^fence...|(`+)(?!`)[\s\S]*?(?<!`)\2(?!`)` (gm), but a code span's closing run
 * is looked up in an index of backtick runs instead of by lazy backtracking,
 * which was quadratic on a long unclosed backtick run (CodeQL js/polynomial-redos).
 */
function protectCode(input, protect) {
  // Maximal backtick runs by length, ascending start offsets: a span closes at
  // the first later run of exactly its opening length.
  const runs = new Map();
  for (const match of input.matchAll(/`+/g)) {
    const starts = runs.get(match[0].length) ?? [];
    starts.push(match.index);
    runs.set(match[0].length, starts);
  }
  const cursors = new Map();
  let out = "";
  let last = 0;
  let runEnd = -1;
  let p = 0;
  // A fence needs a newline after its opening line; without one the fence
  // pattern can only fail, after backtracking across the whole line.
  let nextNewline = input.indexOf("\n");
  while (p < input.length) {
    if (nextNewline !== -1 && nextNewline < p)
      nextNewline = input.indexOf("\n", p);
    if ((p === 0 || input[p - 1] === "\n") && nextNewline !== -1) {
      FENCE.lastIndex = p;
      const fence = FENCE.exec(input);
      if (fence && fence[0]) {
        out += input.slice(last, p) + protect(fence[0]);
        p = last = p + fence[0].length;
        continue;
      }
    }
    if (input[p] === "`") {
      if (p >= runEnd) {
        runEnd = p;
        while (input[runEnd] === "`") runEnd++;
      }
      // An opening inside a longer run starts mid-run, as the regex retried there.
      const length = runEnd - p;
      const starts = runs.get(length) ?? [];
      let index = cursors.get(length) ?? 0;
      while (index < starts.length && starts[index] < runEnd) index++;
      cursors.set(length, index);
      if (index < starts.length) {
        const end = starts[index] + length;
        out += input.slice(last, p) + protect(input.slice(p, end));
        p = last = end;
        continue;
      }
    }
    p++;
  }
  return out + input.slice(last);
}

// Protected-unit keys: a prefix the input does not contain, the unit's index in
// base 254 over U+E002..U+E0FF, then U+E001. Private-use characters match no
// repair pattern, and the keys stay short however many units a note holds.
const KEY_BASE = 254;
function keyDigits(index) {
  let digits = "";
  do {
    digits = String.fromCharCode(0xe002 + (index % KEY_BASE)) + digits;
    index = Math.floor(index / KEY_BASE);
  } while (index > 0);
  return digits;
}

function repairPass(input, knownIDs) {
  const valid = new Set(knownIDs);
  const protectedUnits = new Map();
  let prefix = "\uE000";
  while (input.includes(prefix)) prefix += "\uE000";
  const protect = (value) => {
    const key = `${prefix}${keyDigits(protectedUnits.size)}\uE001`;
    protectedUnits.set(key, value);
    return key;
  };
  const marker = "\0";
  let text = protectCode(input, protect);
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
      /^(?:spk|speaker)[ _]\p{Nd}+:?$/iu.test(content) ||
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
      new RegExp(`(?<![\\p{L}\\p{N}_-])${escaped}(?![\\p{L}\\p{N}_-])`, "gu"),
      marker
    );
  }
  // Word boundaries and digits are Unicode, as in Python generation and Swift
  // (ICU): an ID or speaker label glued to CJK text is part of a word, not a
  // citation, and `Speaker_١٢` is a speaker label.
  text = text.replace(
    /(?<![\p{L}\p{N}_])(?:spk|speaker)[ _]\p{Nd}+(?![\p{L}\p{N}_]):?[ \t]*/giu,
    marker
  );
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
  // One pass, restoring nested units (a link label that held a code span) recursively.
  const keyPattern = new RegExp(`${prefix}[\\uE002-\\uE0FF]+\\uE001`, "g");
  const restore = (value) =>
    value.replace(keyPattern, (key) =>
      protectedUnits.has(key) ? restore(protectedUnits.get(key)) : key
    );
  text = restore(text);
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

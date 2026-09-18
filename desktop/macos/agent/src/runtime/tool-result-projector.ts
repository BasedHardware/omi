import { toolManifestEntry, type OmiToolSurface } from "./omi-tool-manifest.js";

export const DEFAULT_MODEL_TOOL_RESULT_BUDGET_BYTES = 8 * 1024;
export const PURPOSE_RANKING_FLAG = "OMI_TOOL_RESULT_PURPOSE_RANKING_ENABLED";

export interface ProjectedToolPayload {
  text: string;
  omitted: Record<string, number>;
}

const incompleteProjections = new WeakSet<ProjectedToolPayload>();

export function projectionIsComplete(payload: ProjectedToolPayload): boolean {
  return !incompleteProjections.has(payload)
    && Object.values(payload.omitted).every((count) => count === 0);
}

interface TypedSection {
  name: string;
  total: number;
  items: unknown[];
}

export function toolResultBudgetBytes(toolName: string, surface: OmiToolSurface): number {
  return toolManifestEntry(toolName)?.resultContract?.budgets[surface]
    ?? DEFAULT_MODEL_TOOL_RESULT_BUDGET_BYTES;
}

/**
 * Total, deterministic projection. The first item in every non-empty section is
 * reserved before lower-priority sections may consume the remaining budget.
 * Oversize items are UTF-8-safely excerpted and still count as one shown item.
 */
export function projectToolResultPayload(input: {
  toolName: string;
  result: string;
  purpose?: string;
  maxBytes: number;
  purposeRankingEnabled?: boolean;
}): ProjectedToolPayload {
  const contract = toolManifestEntry(input.toolName)?.resultContract;
  const rankingEnabled = input.purposeRankingEnabled
    ?? process.env[PURPOSE_RANKING_FLAG] === "1";
  const rankByPurpose = rankingEnabled && contract?.ranking === "purpose_then_recency";
  const sectionPriority = new Map((contract?.sections ?? []).map((name, index) => [name, index]));
  const maxItems = contract?.maxItemsPerSection ?? Number.MAX_SAFE_INTEGER;
  const sections = extractSections(input.result, input.toolName)
    .sort((a, b) => (sectionPriority.get(a.name) ?? Number.MAX_SAFE_INTEGER)
      - (sectionPriority.get(b.name) ?? Number.MAX_SAFE_INTEGER))
    .map((section) => ({
      ...section,
      items: (rankByPurpose && input.purpose ? rankItems(section.items, input.purpose) : section.items)
        .slice(0, maxItems),
    }));
  const populated = sections.filter((section) => section.items.length > 0).length;
  const fairItemBytes = Math.min(1_024, Math.max(64, Math.floor(input.maxBytes / Math.max(1, populated * 3))));
  const shown = new Map(sections.map((section) => [section.name, 0]));
  const rendered = new Map<string, string[]>();
  const renderedCompletely = new Map<string, boolean[]>();

  // Reserve useful content for every populated section before filling by priority.
  for (const section of sections) {
    if (section.items.length > 0) {
      const first = renderItemExcerpt(section.items[0], fairItemBytes);
      rendered.set(section.name, [first.text]);
      renderedCompletely.set(section.name, [first.complete]);
      shown.set(section.name, 1);
    } else {
      rendered.set(section.name, []);
      renderedCompletely.set(section.name, []);
    }
  }

  let payload = renderProjection(sections, rendered, shown);
  while (!fits(payload, input.maxBytes) && fairItemBytes > 0) {
    const longest = sections
      .filter((section) => (rendered.get(section.name)?.length ?? 0) > 0)
      .sort((a, b) => Buffer.byteLength(rendered.get(b.name)![0], "utf8")
        - Buffer.byteLength(rendered.get(a.name)![0], "utf8"))[0];
    if (!longest) break;
    const current = rendered.get(longest.name)![0];
    const nextLimit = Buffer.byteLength(current, "utf8") - 16;
    if (nextLimit < 16) break;
    const next = renderItemExcerpt(longest.items[0], nextLimit);
    rendered.get(longest.name)![0] = next.text;
    renderedCompletely.get(longest.name)![0] = next.complete;
    payload = renderProjection(sections, rendered, shown);
  }

  if (!fits(payload, input.maxBytes)) {
    // This is only reachable for an unrealistically tiny budget. It remains a
    // successful, fitting projection rather than throwing or manufacturing ok:false.
    const omitted = Object.fromEntries(sections.map((section) => [section.name, section.total]));
    const minimal = { text: "Tool result available via fullOutputRef.", omitted };
    const fallback = fits(minimal, input.maxBytes) ? minimal : { text: "", omitted: {} };
    incompleteProjections.add(fallback);
    return fallback;
  }

  for (const section of sections) {
    for (let index = 1; index < section.items.length; index += 1) {
      const current = rendered.get(section.name)!;
      const next = renderItemExcerpt(section.items[index], fairItemBytes);
      current.push(next.text);
      renderedCompletely.get(section.name)!.push(next.complete);
      shown.set(section.name, current.length);
      const candidate = renderProjection(sections, rendered, shown);
      if (!fits(candidate, input.maxBytes)) {
        current.pop();
        renderedCompletely.get(section.name)!.pop();
        shown.set(section.name, current.length);
        break;
      }
      payload = candidate;
    }
  }
  const excerpted = [...renderedCompletely.values()].some((items) => items.some((complete) => !complete));
  if (excerpted) incompleteProjections.add(payload);
  return payload;
}

function renderProjection(
  sections: TypedSection[],
  rendered: Map<string, string[]>,
  shown: Map<string, number>,
): ProjectedToolPayload {
  const omitted = Object.fromEntries(sections.map((section) => [
    section.name,
    Math.max(0, section.total - (shown.get(section.name) ?? 0)),
  ]));
  const text = sections.flatMap((section) => {
    const count = shown.get(section.name) ?? 0;
    return [
      `${section.name} (${section.total} total)`,
      ...(rendered.get(section.name) ?? []).map((item) => `- ${item}`),
      `[${section.name}: ${count} shown, ${omitted[section.name]} omitted]`,
    ];
  }).join("\n");
  return { text, omitted };
}

function extractSections(result: string, toolName: string): TypedSection[] {
  let parsed: unknown;
  try { parsed = JSON.parse(result); } catch { parsed = null; }
  if (isRecord(parsed) && Array.isArray(parsed.sections)) {
    const sections = parsed.sections.flatMap((value): TypedSection[] => {
      if (!isRecord(value) || typeof value.name !== "string" || !Array.isArray(value.items)) return [];
      const total = integer(value.total) ?? value.items.length;
      return [{ name: value.name, total: Math.max(total, value.items.length), items: value.items }];
    });
    if (sections.length > 0) {
      const siblings = Object.fromEntries(Object.entries(parsed).filter(([key]) => ![
        "ok", "tool", "totals", "sections", "toolResultEnvelope",
      ].includes(key)));
      if (Object.keys(siblings).length > 0) {
        sections.push({ name: "meta", total: 1, items: [siblings] });
      }
      return sections;
    }
  }
  if (isRecord(parsed)) {
    const arrays = Object.entries(parsed).filter(([, value]) => Array.isArray(value));
    if (arrays.length > 0) {
      return arrays.map(([name, items]) => ({ name, total: (items as unknown[]).length, items: items as unknown[] }));
    }
    return [{ name: toolName === "get_daily_recap" ? "summary" : "result", total: 1, items: [parsed] }];
  }
  return [{ name: "text", total: 1, items: [result] }];
}

function renderItemExcerpt(value: unknown, maxBytes: number): { text: string; complete: boolean } {
  if (!isRecord(value)) {
    const full = renderItem(value);
    const text = utf8Excerpt(full, maxBytes);
    return { text, complete: text === full };
  }

  // Swift encodes typed items with sorted keys, so byte-prefixing the JSON can
  // put a large `content` field before title/summary/source identity. Render
  // those semantic fields explicitly first and spend only the remaining bytes
  // on content. This is deliberately independent of object insertion order.
  const parts: string[] = [];
  const fullParts: string[] = [];
  const renderedReservedKeys = new Set<string>();
  const append = (key: string, label: string, field: unknown, budget: number) => {
    if (typeof field !== "string" || field.length === 0) return;
    const normalized = field.replace(/\s+/g, " ").trim();
    if (normalized.length === 0) return;
    parts.push(`${label}: ${utf8Excerpt(normalized, budget)}`);
    fullParts.push(`${label}: ${normalized}`);
    renderedReservedKeys.add(key);
  };
  append("title", "title", value.title, Math.max(16, Math.floor(maxBytes * 0.28)));
  append("summary", "summary", value.summary, Math.max(16, Math.floor(maxBytes * 0.36)));
  append("citationMarker", "citation", value.citationMarker, 48);
  append("sourceId", "sourceId", value.sourceId, 96);
  if (typeof value.content === "string" && value.content.length > 0) {
    renderedReservedKeys.add("content");
  }

  // Content is the only separately budgeted excerpt. Every other item field
  // remains in the identity segment so a typed recap cannot silently lose
  // minutes/captures, task priority, focus status, memory category, or future
  // scalar fields while claiming the item was rendered completely.
  for (const [key, field] of Object.entries(value)) {
    if (renderedReservedKeys.has(key)) continue;
    if (field === undefined) continue;
    const renderedField = typeof field === "string"
      ? field.replace(/\s+/g, " ").trim()
      : renderItem(field);
    parts.push(`${key}=${renderedField}`);
    fullParts.push(`${key}=${renderedField}`);
  }

  const identity = parts.join(" | ");
  const separator = identity.length > 0 ? " | " : "";
  const remaining = Math.max(0, maxBytes - Buffer.byteLength(identity + separator + "content: ", "utf8"));
  if (typeof value.content === "string" && value.content.length > 0 && remaining > 0) {
    parts.push(`content: ${utf8Excerpt(value.content.replace(/\s+/g, " ").trim(), remaining)}`);
  }
  if (typeof value.content === "string" && value.content.length > 0) {
    fullParts.push(`content: ${value.content.replace(/\s+/g, " ").trim()}`);
  }
  const full = fullParts.length > 0 ? fullParts.join(" | ") : renderItem(value);
  const text = parts.length > 0 ? utf8Excerpt(parts.join(" | "), maxBytes) : utf8Excerpt(full, maxBytes);
  return { text, complete: text === full };
}

function renderItem(value: unknown): string {
  if (typeof value === "string") return value.replace(/\s+/g, " ").trim();
  try { return JSON.stringify(value); } catch { return String(value); }
}

export function utf8Excerpt(value: string, maxBytes: number): string {
  if (Buffer.byteLength(value, "utf8") <= maxBytes) return value;
  const ellipsis = "…";
  const contentBudget = Math.max(0, maxBytes - Buffer.byteLength(ellipsis, "utf8"));
  let bytes = 0;
  let result = "";
  for (const character of value) {
    const size = Buffer.byteLength(character, "utf8");
    if (bytes + size > contentBudget) break;
    result += character;
    bytes += size;
  }
  return `${result}${ellipsis}`;
}

function rankItems(items: unknown[], purpose: string): unknown[] {
  const terms = new Set(purpose.toLowerCase().match(/[a-z0-9]{3,}/g) ?? []);
  return items.map((item, index) => ({ item, index, score: lexicalScore(renderItem(item), terms) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ item }) => item);
}

function lexicalScore(value: string, terms: Set<string>): number {
  const haystack = value.toLowerCase();
  let score = 0;
  for (const term of terms) if (haystack.includes(term)) score += 1;
  return score;
}

function fits(value: ProjectedToolPayload, maxBytes: number): boolean {
  return Buffer.byteLength(JSON.stringify(value), "utf8") <= Math.max(0, maxBytes);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function integer(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

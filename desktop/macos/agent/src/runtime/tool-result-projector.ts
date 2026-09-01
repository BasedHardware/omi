import { toolManifestEntry, type OmiToolSurface } from "./omi-tool-manifest.js";

export const DEFAULT_MODEL_TOOL_RESULT_BUDGET_BYTES = 8 * 1024;
export const PURPOSE_RANKING_FLAG = "OMI_TOOL_RESULT_PURPOSE_RANKING_ENABLED";
export const DIGEST_FLAG = "OMI_TOOL_RESULT_DIGEST_ENABLED";

export interface ProjectedToolPayload {
  text: string;
  omitted: Record<string, number>;
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
 * Total, deterministic projection. A budget can reduce detail but can never
 * change executor success into failure. Every section closes with its total
 * and omitted count so absence is never confused with an empty executor result.
 */
export function projectToolResultPayload(input: {
  toolName: string;
  result: string;
  purpose?: string;
  maxBytes: number;
  purposeRankingEnabled?: boolean;
}): ProjectedToolPayload {
  const sections = extractSections(input.result, input.toolName);
  const rankByPurpose = input.purposeRankingEnabled
    ?? process.env[PURPOSE_RANKING_FLAG] === "1";
  const ranked = sections.map((section) => ({
    ...section,
    items: rankByPurpose && input.purpose ? rankItems(section.items, input.purpose) : section.items,
  }));
  const omitted: Record<string, number> = Object.fromEntries(ranked.map((section) => [section.name, section.total]));
  const lines: string[] = [];

  for (const section of ranked) {
    const header = `${section.name} (${section.total} total)`;
    if (fits({ text: [...lines, header].join("\n"), omitted }, input.maxBytes)) lines.push(header);
    let included = 0;
    for (const item of section.items) {
      const line = `- ${renderItem(item)}`;
      const nextOmitted = { ...omitted, [section.name]: Math.max(0, section.total - included - 1) };
      if (!fits({ text: [...lines, line].join("\n"), omitted: nextOmitted }, input.maxBytes)) break;
      lines.push(line);
      included += 1;
      omitted[section.name] = Math.max(0, section.total - included);
    }
    const closure = `[${section.name}: ${included} shown, ${omitted[section.name] ?? 0} omitted]`;
    if (fits({ text: [...lines, closure].join("\n"), omitted }, input.maxBytes)) lines.push(closure);
  }

  let payload: ProjectedToolPayload = { text: lines.join("\n"), omitted };
  if (fits(payload, input.maxBytes)) return payload;
  payload = { text: "Tool result projected to fit the surface budget.", omitted };
  if (fits(payload, input.maxBytes)) return payload;
  return { text: "", omitted: {} };
}

/** Optional digest lane. Timeout, rejection, or oversize returns the ranked projection. */
export async function projectToolResultWithDigest(input: {
  fallback: ProjectedToolPayload;
  budgetBytes: number;
  timeoutMs: number;
  digest: () => Promise<string>;
  enabled?: boolean;
}): Promise<ProjectedToolPayload> {
  const enabled = input.enabled ?? process.env[DIGEST_FLAG] === "1";
  if (!enabled) return input.fallback;
  let timer: NodeJS.Timeout | undefined;
  try {
    const text = await Promise.race([
      input.digest(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("digest_timeout")), input.timeoutMs);
      }),
    ]);
    const candidate = { text, omitted: input.fallback.omitted };
    return fits(candidate, input.budgetBytes) ? candidate : input.fallback;
  } catch {
    return input.fallback;
  } finally {
    if (timer) clearTimeout(timer);
  }
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
    if (sections.length > 0) return sections;
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

function renderItem(value: unknown): string {
  if (typeof value === "string") return value.replace(/\s+/g, " ").trim();
  try { return JSON.stringify(value); } catch { return String(value); }
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

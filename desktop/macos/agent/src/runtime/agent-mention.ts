// Mechanical agent-mention extraction.
//
// `DesktopIntentRouter` documents that it "intentionally has no language
// heuristics": surfaces hand it `syntaxFacts.explicitProvider` and the kernel
// re-resolves that name against `availableAdapterIds`. Nothing ever populated
// that field, so "use codex to fix this test" reached the router as an ordinary
// sentence and ran on the default adapter.
//
// This module is the surface-side extractor that fills the gap. It is a literal
// alias table matched on word boundaries — no model, no scoring, no inference.
// It stays *outside* the router on purpose: keeping string matching at the
// surface preserves the router's no-heuristics contract. What comes out is a
// proposal; the kernel still re-resolves and authorizes it.

import type { ProductionAdapterId } from "../adapters/interface.js";

/**
 * Agents a user can name out loud.
 *
 * Every production adapter is mentionable. The alias table below must stay
 * exhaustive over `ProductionAdapterId` — the `Record` type enforces that, so
 * adding an adapter without giving it a spoken name is a compile error rather
 * than an agent users can never ask for by name.
 */
export type MentionableAgentId = ProductionAdapterId;

export interface AgentMention {
  readonly adapterId: MentionableAgentId;
  /** The literal text that matched, as written by the user. */
  readonly alias: string;
  /** Offset of the match in the utterance. */
  readonly index: number;
  /** True when the surrounding phrasing rules this agent *out* ("not codex"). */
  readonly negated: boolean;
}

/**
 * Aliases per agent, lower-cased. Order within an agent does not matter —
 * matching always tries longer aliases first so "claude code" wins over
 * "claude".
 */
const AGENT_ALIASES: Record<MentionableAgentId, readonly string[]> = {
  acp: ["claude code", "claude-code", "claudecode", "claude"],
  "pi-mono": ["pi-mono", "pi mono", "pimono", "omi ai"],
  hermes: ["hermes"],
  openclaw: ["openclaw", "open claw", "open-claw"],
  codex: ["codex"],
};

/**
 * Words that, appearing shortly before an agent name, mean the user is ruling
 * it out rather than asking for it. Mirrors the router's existing
 * `delegationNegated` idea, but per-agent so "not codex, use hermes" keeps
 * hermes.
 */
const NEGATORS: ReadonlySet<string> = new Set([
  "not",
  "dont",
  "doesnt",
  "didnt",
  "cant",
  "wont",
  "no",
  "never",
  "without",
  "avoid",
  "skip",
  "except",
  "besides",
  "unlike",
  // "use hermes instead of codex" rules out codex, so this negates rather than
  // ending the clause.
  "instead",
]);

/**
 * How many words before a mention are scanned for a negator, within the current
 * clause. Four covers the natural phrasings ("instead of codex", "do not use
 * codex").
 */
const NEGATION_LOOKBACK_WORDS = 4;

/**
 * A negator binds only inside its own clause. Without this, "don't use codex,
 * use hermes" would drag the "don't" onto hermes and rule out both agents.
 * Plain hyphens are excluded so hyphenated aliases stay intact.
 */
const CLAUSE_BOUNDARY = /[,;:.!?—–\n]|\bbut\b/g;

interface CompiledAlias {
  readonly adapterId: MentionableAgentId;
  readonly alias: string;
  readonly pattern: RegExp;
}

/**
 * Longest-alias-first so a longer name consumes its own prefix: "claude code"
 * must not be reported as a bare "claude" mention.
 */
const COMPILED_ALIASES: readonly CompiledAlias[] = Object.entries(AGENT_ALIASES)
  .flatMap(([adapterId, aliases]) =>
    aliases.map((alias) => ({ adapterId: adapterId as MentionableAgentId, alias })),
  )
  .sort((left, right) => right.alias.length - left.alias.length)
  .map(({ adapterId, alias }) => ({
    adapterId,
    alias,
    // `\b` on both sides keeps "hermeneutics" from matching "hermes" and lets
    // punctuation or an "@" prefix bound the name naturally.
    pattern: new RegExp(`\\b${escapeRegExp(alias)}\\b`, "gi"),
  }));

/**
 * Every agent named in the utterance, in the order they appear. Overlapping
 * matches are resolved in favour of the longer alias.
 */
export function extractAgentMentions(utterance: string): readonly AgentMention[] {
  if (!utterance.trim()) return [];

  const claimed: { start: number; end: number }[] = [];
  const mentions: AgentMention[] = [];

  for (const { adapterId, pattern } of COMPILED_ALIASES) {
    pattern.lastIndex = 0;
    for (let match = pattern.exec(utterance); match; match = pattern.exec(utterance)) {
      const start = match.index;
      const end = start + match[0].length;
      // A longer alias already covering this span wins; skip the shorter one.
      if (claimed.some((span) => start < span.end && end > span.start)) continue;
      claimed.push({ start, end });
      mentions.push({
        adapterId,
        alias: match[0],
        index: start,
        negated: isNegated(utterance.slice(0, start)),
      });
    }
  }

  return mentions.sort((left, right) => left.index - right.index);
}

/**
 * The value a surface should put in `DesktopIntentSyntaxFacts.explicitProvider`.
 *
 * First non-negated mention wins. When a user names two agents in one breath
 * ("try codex or hermes") the first is treated as the request and the rest is
 * left to the kernel's own fallback ordering — this extractor never ranks.
 * Returns null when no agent is named, or when every mention was negated.
 */
export function explicitProviderFrom(utterance: string): MentionableAgentId | null {
  const requested = extractAgentMentions(utterance).find((mention) => !mention.negated);
  return requested?.adapterId ?? null;
}

/**
 * Agents the user ruled out. These must be dropped from the fallback chain as
 * well as from selection — "don't use hermes" is not honoured by a runtime that
 * merely starts somewhere else and then falls back to Hermes.
 *
 * An agent both ruled out and asked for ("not hermes... ok, hermes") counts as
 * asked for; the later request wins over the earlier exclusion.
 */
export function negatedAgentsFrom(utterance: string): readonly MentionableAgentId[] {
  const mentions = extractAgentMentions(utterance);
  const requested = new Set(
    mentions.filter((mention) => !mention.negated).map((mention) => mention.adapterId),
  );
  return [
    ...new Set(
      mentions
        .filter((mention) => mention.negated && !requested.has(mention.adapterId))
        .map((mention) => mention.adapterId),
    ),
  ];
}

function isNegated(before: string): boolean {
  const words = currentClause(before.toLowerCase())
    // Drop apostrophes rather than splitting on them, so "don't" stays one word
    // and matches the "dont" negator instead of becoming "don" + "t".
    .replace(/['’]/g, "")
    .split(/[^a-z]+/)
    .filter(Boolean);
  return words
    .slice(-NEGATION_LOOKBACK_WORDS)
    .some((word) => NEGATORS.has(word));
}

/** Everything after the last clause boundary in the text preceding a mention. */
function currentClause(before: string): string {
  CLAUSE_BOUNDARY.lastIndex = 0;
  let clauseStart = 0;
  for (let match = CLAUSE_BOUNDARY.exec(before); match; match = CLAUSE_BOUNDARY.exec(before)) {
    clauseStart = match.index + match[0].length;
  }
  return before.slice(clauseStart);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

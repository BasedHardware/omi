import type { SourceIdentityRef } from "../schema";

export interface SourceMention { mention_ref: string; text: string; source_identity_ref: SourceIdentityRef | null; speaker_rendering: string | null; }
export interface MentionRequest { strategy: "mention-local-handle"; version: "v1"; mentions: readonly SourceMention[]; }
export interface MentionModelResponse { links: readonly { mention_ref: string; antecedent_mention_ref: string | null; uncertainty: readonly string[] }[]; }
export interface LocalHandle { handle: string; mention_ref: string; antecedent_handle: string | null; uncertainty: readonly string[]; }

/** Pure request construction; callers may send this to any injected edge adapter. */
export const buildMentionRequest = (mentions: readonly SourceMention[]): MentionRequest => ({ strategy: "mention-local-handle", version: "v1", mentions });

/** Pure parse/validate/transition planning. A bare reference stays source-local and unresolved. */
export const planLocalHandles = (request: MentionRequest, response: MentionModelResponse): LocalHandle[] => {
  const known = new Set(request.mentions.map((mention) => mention.mention_ref));
  const links = new Map(response.links.map((link) => [link.mention_ref, link]));
  return request.mentions.map((mention) => {
    const link = links.get(mention.mention_ref);
    const antecedent = link?.antecedent_mention_ref;
    const resolvable = antecedent !== null && antecedent !== undefined && known.has(antecedent);
    return {
      handle: `local:${mention.mention_ref}`,
      mention_ref: mention.mention_ref,
      antecedent_handle: resolvable ? `local:${antecedent}` : null,
      uncertainty: resolvable ? link!.uncertainty : [...(link?.uncertainty ?? []), "unresolved_local_mention"],
    };
  });
};

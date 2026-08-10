/** Host-readable evidence derived only from the currently rendered live surface. */

export const CONSUMER_EVIDENCE_ROUTES = [
  "memories",
  "tasks",
  "conversations",
  "folders",
  "listen",
  "chat",
  "settings",
] as const;

export type ConsumerEvidenceRoute = typeof CONSUMER_EVIDENCE_ROUTES[number];

export type RenderedConsumerObservation = {
  readonly route: ConsumerEvidenceRoute;
  readonly state: "ready";
  readonly semantic: string;
  readonly transcript?: string;
};

const MAX_SEMANTIC_LENGTH = 256;
const MAX_TRANSCRIPT_LENGTH = 1_024;

function route(value: string | undefined): ConsumerEvidenceRoute | null {
  return CONSUMER_EVIDENCE_ROUTES.includes(value as ConsumerEvidenceRoute)
    ? value as ConsumerEvidenceRoute
    : null;
}

function bounded(value: string | undefined, limit: number): string | null {
  if (value === undefined || value.length > limit || value.trim() === "") return null;
  return value;
}

/**
 * Read the narrow semantic markers a production component placed on its root.
 * No textContent query exists here: arbitrary DOM copy, prompts, account data,
 * attachment metadata, and credentials cannot enter this contract by accident.
 */
export function readRenderedConsumerObservation(
  root: Pick<ParentNode, "querySelector">,
): RenderedConsumerObservation | null {
  const surface = root.querySelector<HTMLElement>("main[data-production-shell='true']");
  if (surface === null) return null;
  const renderedRoute = route(surface.dataset["route"]);
  if (
    renderedRoute === null
    || surface.dataset["surfaceState"] !== "ready"
    || surface.dataset["qaFixture"] !== "none"
  ) return null;

  const semantic = bounded(surface.dataset["consumerSemantic"], MAX_SEMANTIC_LENGTH);
  if (semantic === null) return null;
  const transcript = bounded(surface.dataset["consumerTranscript"], MAX_TRANSCRIPT_LENGTH);
  if (renderedRoute === "listen") {
    return transcript === null
      ? null
      : { route: renderedRoute, state: "ready", semantic, transcript };
  }
  if (surface.dataset["consumerTranscript"] !== undefined) return null;
  return { route: renderedRoute, state: "ready", semantic };
}

export function boundedRenderedTranscript(
  segments: readonly { readonly text: string }[],
): string {
  return segments
    .slice(-4)
    .map((segment) => segment.text.replace(/\s+/gu, " ").trim().slice(0, 240))
    .filter((text) => text !== "")
    .join(" ")
    .slice(0, MAX_TRANSCRIPT_LENGTH);
}

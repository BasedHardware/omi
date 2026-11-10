import type { VoicePopulation } from "@/lib/telemetry/aggregates";
import { isUtcDay } from "@/lib/telemetry/aggregates";

/**
 * Replacement reliability reader. Default off.
 * Independent of transport shadow and retirement flags: this module does not
 * read those switches, and they cannot enable this reader.
 */
export const RELIABILITY_REPLACEMENT_READER_ENV =
  "RELIABILITY_REPLACEMENT_READER";
export const RELIABILITY_REPLACEMENT_CUTOVER_ENV =
  "RELIABILITY_REPLACEMENT_CUTOVER";
export const RELIABILITY_REPLACEMENT_POPULATION_ENV =
  "RELIABILITY_REPLACEMENT_POPULATION";

export interface ReliabilityReaderConfig {
  enabled: boolean;
  /** Inclusive UTC day. Null keeps the reader off so days are never mixed. */
  cutover: string | null;
  population: VoicePopulation;
}

export function reliabilityReaderConfig(
  env: Record<string, string | undefined> = process.env
): ReliabilityReaderConfig {
  const requested = (env[RELIABILITY_REPLACEMENT_READER_ENV] ?? "")
    .trim()
    .toLowerCase();
  const cutover = (env[RELIABILITY_REPLACEMENT_CUTOVER_ENV] ?? "").trim();
  const populationRaw = (
    env[RELIABILITY_REPLACEMENT_POPULATION_ENV] ?? ""
  ).trim();
  const population: VoicePopulation =
    populationRaw === "floating_voice" ? "floating_voice" : "physical_shortcut";
  const enabled = requested === "on" && isUtcDay(cutover);
  return {
    enabled,
    cutover: enabled ? cutover : null,
    population,
  };
}

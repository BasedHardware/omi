import {
  parseObservabilitySinkMode,
  type ObservabilitySinkMode,
} from "../src/observability";
import { verifyReady } from "./verify-ready";

export type ReleaseGateInput = {
  readyUrl: string;
  environment: string;
  sinkMode: ObservabilitySinkMode;
  betterStackEvidence?: string;
};

export type ReleaseGateParseResult =
  | { kind: "ok"; value: ReleaseGateInput }
  | { kind: "error"; reason: string };

const evidencePattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const environmentPattern = /^[a-z][a-z0-9_-]{0,63}$/;

export function parseReleaseGateArgs(args: string[]): ReleaseGateParseResult {
  const readyUrl = args[0];
  if (readyUrl === undefined || readyUrl.length === 0)
    return { kind: "error", reason: "ready_url_required" };
  const options = new Map<string, string>();
  for (let index = 1; index < args.length; index += 2) {
    const option = args[index];
    const value = args[index + 1];
    if (option === undefined || value === undefined)
      return { kind: "error", reason: "option_value_required" };
    if (
      option !== "--environment" &&
      option !== "--observability-sink-mode" &&
      option !== "--better-stack-evidence"
    ) {
      return { kind: "error", reason: "unknown_option" };
    }
    if (options.has(option))
      return { kind: "error", reason: "duplicate_option" };
    options.set(option, value);
  }
  const environment = options.get("--environment");
  if (environment === undefined || !environmentPattern.test(environment))
    return { kind: "error", reason: "invalid_environment" };
  const sinkMode = parseObservabilitySinkMode(
    options.get("--observability-sink-mode")
  );
  if (sinkMode === null)
    return { kind: "error", reason: "invalid_observability_sink_mode" };
  const betterStackEvidence = options.get("--better-stack-evidence");
  if (sinkMode === "better_stack") {
    if (betterStackEvidence === undefined)
      return { kind: "error", reason: "better_stack_evidence_required" };
    if (!evidencePattern.test(betterStackEvidence))
      return { kind: "error", reason: "invalid_better_stack_evidence" };
  } else if (betterStackEvidence !== undefined) {
    return { kind: "error", reason: "better_stack_evidence_unexpected" };
  }
  return {
    kind: "ok",
    value: {
      readyUrl,
      environment,
      sinkMode,
      ...(betterStackEvidence === undefined ? {} : { betterStackEvidence }),
    },
  };
}

export async function main(args: string[]): Promise<number> {
  const parsed = parseReleaseGateArgs(args);
  if (parsed.kind === "error") {
    console.error(`release gate failed: ${parsed.reason}`);
    return 1;
  }
  const ready = await verifyReady(parsed.value.readyUrl);
  if (
    ready.kind !== "ready" ||
    ready.environment !== parsed.value.environment ||
    ready.sinkMode !== parsed.value.sinkMode
  ) {
    console.error("release gate failed: readiness mismatch");
    return 1;
  }
  console.log(
    `release gate passed: environment=${parsed.value.environment} sink_mode=${parsed.value.sinkMode}`
  );
  return 0;
}

if (import.meta.main) {
  main(Bun.argv.slice(2))
    .then((code) => process.exit(code))
    .catch(() => process.exit(1));
}

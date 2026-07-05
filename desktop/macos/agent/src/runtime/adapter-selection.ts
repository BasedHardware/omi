import { AcpRuntimeAdapter } from "../adapters/acp.js";
import { CodexRuntimeAdapter } from "../adapters/codex.js";
import { HermesRuntimeAdapter } from "../adapters/hermes.js";
import { OpenClawRuntimeAdapter } from "../adapters/openclaw.js";
import { adapterCapabilitiesFor, type AdapterCapabilities, type ProductionAdapterId, type RuntimeAdapter } from "../adapters/interface.js";
import type { AdapterRegistry } from "./adapter-registry.js";

export const ADAPTER_ACTIVATION_ENV = {
  acp: undefined,
  "pi-mono": "OMI_AUTH_TOKEN",
  hermes: "OMI_HERMES_ADAPTER_COMMAND",
  openclaw: "OMI_OPENCLAW_ADAPTER_COMMAND",
  codex: "OMI_CODEX_ADAPTER_COMMAND",
} as const;

export type SelectableAdapterId = keyof typeof ADAPTER_ACTIVATION_ENV;
export const TASK_EXECUTION_ADAPTER_IDS = ["hermes", "openclaw", "codex"] as const;
export type TaskExecutionAdapterId = typeof TASK_EXECUTION_ADAPTER_IDS[number];

const CODE_TASK_ADAPTER_PRIORITY = ["codex", "hermes", "openclaw"] as const satisfies readonly TaskExecutionAdapterId[];
const GENERAL_TASK_ADAPTER_PRIORITY = ["hermes", "openclaw", "codex"] as const satisfies readonly TaskExecutionAdapterId[];

const CODE_RELATED_KEYWORD_PATTERN =
  /\b(bug|debug|fix|implement|implementation|function|method|class|struct|interface|test|tests|refactor|compile|build|lint|typescript|javascript|swift|python|rust|code|repo|stack trace|exception|regression|endpoint)\b/i;
const FILE_NAME_PATTERN =
  /\b[\w.-]+\.(ts|tsx|js|jsx|mjs|cjs|swift|py|rs|go|java|kt|kts|m|mm|h|hpp|cpp|c|cs|dart|rb|php|json|ya?ml|toml|sql|sh|mdx?)\b/i;
const FILE_PATH_PATTERN = /(^|[\s"'(])(?:\.{1,2}\/|~\/|\/|[A-Za-z0-9_.-]+\/)[^\s"'`]+\.[A-Za-z0-9]{1,8}(?=$|[\s"'),.:;])/;
const INLINE_CODE_PATTERN = /```|`[^`]*(?:=>|function|class|def|import|const|let|var|return|\{|\})[^`]*`/i;
const CODE_SYMBOL_PATTERN = /\b(function|func|class|struct|enum|interface|def|async|await|import|export|return|throws?)\b|[{};]\s*$/im;

export interface AdapterAutoSelectionResult {
  adapterId: string;
  fallbackAdapterIds: TaskExecutionAdapterId[];
  reason: string;
  codeLike: boolean;
  connectedAdapterIds: TaskExecutionAdapterId[];
}

export interface AdapterProfile {
  adapterId: ProductionAdapterId;
  activationEnv?: string;
  maxWorkers: number;
  capabilities: AdapterCapabilities;
  createAdapter: (options: { log: (message: string) => void }) => RuntimeAdapter;
}

export const ADAPTER_PROFILES: Record<ProductionAdapterId, AdapterProfile> = {
  acp: {
    adapterId: "acp",
    activationEnv: ADAPTER_ACTIVATION_ENV.acp,
    maxWorkers: 1,
    capabilities: adapterCapabilitiesFor("acp"),
    createAdapter: () => new AcpRuntimeAdapter(),
  },
  "pi-mono": {
    adapterId: "pi-mono",
    activationEnv: ADAPTER_ACTIVATION_ENV["pi-mono"],
    maxWorkers: 1,
    capabilities: adapterCapabilitiesFor("pi-mono"),
    createAdapter: () => {
      throw new Error("pi-mono adapter requires authenticated PiMonoAdapter construction");
    },
  },
  hermes: {
    adapterId: "hermes",
    activationEnv: ADAPTER_ACTIVATION_ENV.hermes,
    maxWorkers: 1,
    capabilities: adapterCapabilitiesFor("hermes"),
    createAdapter: ({ log }) => new HermesRuntimeAdapter({ log }),
  },
  openclaw: {
    adapterId: "openclaw",
    activationEnv: ADAPTER_ACTIVATION_ENV.openclaw,
    maxWorkers: 1,
    capabilities: adapterCapabilitiesFor("openclaw"),
    createAdapter: ({ log }) => new OpenClawRuntimeAdapter({ log }),
  },
  codex: {
    adapterId: "codex",
    activationEnv: ADAPTER_ACTIVATION_ENV.codex,
    maxWorkers: 1,
    capabilities: adapterCapabilitiesFor("codex"),
    createAdapter: ({ log }) => new CodexRuntimeAdapter({ log }),
  },
};

export function adapterIdForHarnessMode(harnessMode: string | undefined): SelectableAdapterId {
  if (harnessMode === undefined) return "acp";
  switch (harnessMode) {
    case "piMono":
    case "pi-mono":
      return "pi-mono";
    case "hermes":
      return "hermes";
    case "openclaw":
    case "openClaw":
      return "openclaw";
    case "codex":
      return "codex";
    case "acp":
      return "acp";
    default:
      throw new Error(`Unknown harness mode: ${harnessMode}`);
  }
}

export function adapterActivationEnv(adapterId: SelectableAdapterId): string | undefined {
  return ADAPTER_PROFILES[adapterId].activationEnv;
}

export function adapterIsActivated(
  adapterId: SelectableAdapterId,
  env: NodeJS.ProcessEnv = process.env
): boolean {
  const activationEnv = adapterActivationEnv(adapterId);
  return activationEnv === undefined || Boolean(env[activationEnv]?.trim());
}

export function adapterProfile(adapterId: ProductionAdapterId): AdapterProfile {
  return ADAPTER_PROFILES[adapterId];
}

export function taskTextLooksCodeRelated(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return (
    CODE_RELATED_KEYWORD_PATTERN.test(trimmed) ||
    FILE_NAME_PATTERN.test(trimmed) ||
    FILE_PATH_PATTERN.test(trimmed) ||
    INLINE_CODE_PATTERN.test(trimmed) ||
    CODE_SYMBOL_PATTERN.test(trimmed)
  );
}

export function selectBestAdapterForTask(input: {
  prompt: string;
  defaultAdapterId: string;
  connectedAdapterIds: readonly TaskExecutionAdapterId[];
}): AdapterAutoSelectionResult {
  const codeLike = taskTextLooksCodeRelated(input.prompt);
  const priority = codeLike ? CODE_TASK_ADAPTER_PRIORITY : GENERAL_TASK_ADAPTER_PRIORITY;
  const connected = new Set(input.connectedAdapterIds);
  const connectedAdapterIds = TASK_EXECUTION_ADAPTER_IDS.filter((adapterId) => connected.has(adapterId));
  const selectedAdapterId = priority.find((adapterId) => connected.has(adapterId));
  if (!selectedAdapterId) {
    return {
      adapterId: input.defaultAdapterId,
      fallbackAdapterIds: [],
      reason: "default_no_connected_task_adapters",
      codeLike,
      connectedAdapterIds,
    };
  }
  return {
    adapterId: selectedAdapterId,
    fallbackAdapterIds: priority.filter((adapterId) => adapterId !== selectedAdapterId && connected.has(adapterId)),
    reason: `${codeLike ? "code" : "general"}_task_${selectedAdapterId}`,
    codeLike,
    connectedAdapterIds,
  };
}

export function adapterActivationError(adapterId: ProductionAdapterId): string | undefined {
  const envName = adapterActivationEnv(adapterId);
  if (!envName) return undefined;
  const label = adapterId === "pi-mono" ? "pi-mono" : adapterId === "openclaw" ? "OpenClaw" : adapterId === "codex" ? "Codex" : "Hermes";
  if (adapterId === "codex") {
    return "Codex is not available. Install the Codex CLI, sign in, then try again.";
  }
  if (adapterId === "hermes" || adapterId === "openclaw") {
    return `${label} is not available. Make sure ${label} is installed first, then try again.`;
  }
  return `${label} adapter is unavailable.`;
}

export function ensureRegisteredAdapter(
  registry: AdapterRegistry,
  adapterId: ProductionAdapterId,
  options: {
    log: (message: string) => void;
    maxWorkers?: number;
    onCreate?: (adapter: RuntimeAdapter) => void;
  }
): boolean {
  if (!adapterIsActivated(adapterId)) return false;
  if (registry.has(adapterId)) return true;
  const profile = adapterProfile(adapterId);
  registry.register(adapterId, () => {
    const adapter = profile.createAdapter({ log: options.log });
    options.onCreate?.(adapter);
    return adapter;
  }, options.maxWorkers ?? profile.maxWorkers);
  options.log(`Adapter registered id=${adapterId} tools=${profile.capabilities.supportsTools} maxWorkers=${options.maxWorkers ?? profile.maxWorkers}`);
  return true;
}

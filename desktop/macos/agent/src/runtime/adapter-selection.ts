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
export const TASK_EXECUTION_ADAPTER_IDS = ["acp", "hermes", "openclaw", "codex"] as const;
export type TaskExecutionAdapterId = typeof TASK_EXECUTION_ADAPTER_IDS[number];

const DEEP_CODEBASE_TASK_ADAPTER_PRIORITY = ["acp", "codex", "hermes", "openclaw"] as const satisfies readonly TaskExecutionAdapterId[];
const TERMINAL_NATIVE_TASK_ADAPTER_PRIORITY = ["codex", "acp", "hermes", "openclaw"] as const satisfies readonly TaskExecutionAdapterId[];
const STRAIGHTFORWARD_CODE_TASK_ADAPTER_PRIORITY = ["codex", "acp", "hermes", "openclaw"] as const satisfies readonly TaskExecutionAdapterId[];
const GENERAL_TASK_ADAPTER_PRIORITY = ["hermes", "openclaw", "codex", "acp"] as const satisfies readonly TaskExecutionAdapterId[];

const CODE_RELATED_KEYWORD_PATTERN =
  /\b(bug|debug|fix|implement|implementation|function|method|class|struct|interface|test|tests|refactor|compile|build|lint|typescript|javascript|swift|python|rust|code|repo|stack trace|exception|regression|endpoint)\b/i;
const FILE_NAME_PATTERN =
  /\b[\w.-]+\.(ts|tsx|js|jsx|mjs|cjs|swift|py|rs|go|java|kt|kts|m|mm|h|hpp|cpp|c|cs|dart|rb|php|json|ya?ml|toml|sql|sh|mdx?)\b/i;
const FILE_PATH_PATTERN = /(^|[\s"'(])(?:\.{1,2}\/|~\/|\/|[A-Za-z0-9_.-]+\/)[^\s"'`]+\.[A-Za-z0-9]{1,8}(?=$|[\s"'),.:;])/;
const INLINE_CODE_PATTERN = /```|`[^`]*(?:=>|function|class|def|import|const|let|var|return|\{|\})[^`]*`/i;
const CODE_SYMBOL_PATTERN = /\b(function|func|class|struct|enum|interface|def|async|await|import|export|return|throws?)\b|[{};]\s*$/im;
const CODE_IDENTIFIER_PATTERN =
  /\b(?:[A-Za-z_$][\w$]*_[\w$]+|[a-z_$][\w$]*\d[\w$]*[A-Z][\w$]*|[a-z_$][\w$]*[A-Z][\w$]*\d[\w$]*)\b/;
const CODEBASE_SCOPE_PATTERN =
  /\b(?:multi[-\s]?file|codebase[-\s]?wide|repo(?:sitory)?[-\s]?wide|project[-\s]?wide|cross[-\s]?(?:file|module|service)|across\s+(?:the\s+)?(?:codebase|repo(?:sitory)?|project|files?|modules?|services?|packages?)|across\s+(?:these\s+|the\s+)?(?:\w+\s+){0,4}(?:files?|modules?|services?|packages?))\b/i;
const DEEP_CODE_REASONING_PATTERN =
  /\b(?:trace|root cause|debug(?:ging)?|hard bug|race condition|deadlock|regression|architecture|architectural|plan|planning|design|understand\s+how|interact(?:ion)?|data flow|control flow|call graph|dependency graph|decouple|restructure|redesign|modulari[sz]e)\b/i;
const TERMINAL_NATIVE_TASK_PATTERN =
  /\b(?:ci\/cd|ci|github actions?|workflow|pipeline|docker|kubernetes|k8s|deploy(?:ment)?|release|migration|migrations|dependency|dependencies|lockfile|package-lock|pnpm-lock|yarn\.lock|npm|pnpm|yarn|brew|shell|bash|zsh|terminal|cli|script|makefile|generate\s+(?:docs?|documentation|readme|changelog)|documentation|readme|changelog)\b/i;
const RUN_TECHNICAL_ARTIFACT_PATTERN =
  /\b(?:run|execute|apply)\b[\s\S]{0,80}\b(?:script|command|migration|migrations|test|tests|build|lint|typecheck|workflow|pipeline)\b/i;

export type AdapterSelectionTaskKind = "deep_codebase" | "terminal_devops" | "straightforward_code" | "general";

export interface AdapterAutoSelectionResult {
  adapterId: string;
  fallbackAdapterIds: TaskExecutionAdapterId[];
  reason: string;
  codeLike: boolean;
  taskKind: AdapterSelectionTaskKind;
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
    CODE_SYMBOL_PATTERN.test(trimmed) ||
    CODE_IDENTIFIER_PATTERN.test(trimmed)
  );
}

function taskTextLooksDeepCodebaseRelated(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return CODEBASE_SCOPE_PATTERN.test(trimmed) || (DEEP_CODE_REASONING_PATTERN.test(trimmed) && taskTextLooksCodeRelated(trimmed));
}

function taskTextLooksTerminalNative(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return TERMINAL_NATIVE_TASK_PATTERN.test(trimmed) || RUN_TECHNICAL_ARTIFACT_PATTERN.test(trimmed);
}

export function classifyTaskForAdapterSelection(text: string): AdapterSelectionTaskKind {
  if (taskTextLooksDeepCodebaseRelated(text)) return "deep_codebase";
  if (taskTextLooksTerminalNative(text)) return "terminal_devops";
  if (taskTextLooksCodeRelated(text)) return "straightforward_code";
  return "general";
}

export function selectBestAdapterForTask(input: {
  prompt: string;
  defaultAdapterId: string;
  connectedAdapterIds: readonly TaskExecutionAdapterId[];
}): AdapterAutoSelectionResult {
  const codeLike = taskTextLooksCodeRelated(input.prompt);
  const taskKind = classifyTaskForAdapterSelection(input.prompt);
  const priority =
    taskKind === "deep_codebase"
      ? DEEP_CODEBASE_TASK_ADAPTER_PRIORITY
      : taskKind === "terminal_devops"
        ? TERMINAL_NATIVE_TASK_ADAPTER_PRIORITY
        : taskKind === "straightforward_code"
          ? STRAIGHTFORWARD_CODE_TASK_ADAPTER_PRIORITY
          : GENERAL_TASK_ADAPTER_PRIORITY;
  const connected = new Set(input.connectedAdapterIds);
  const connectedAdapterIds = TASK_EXECUTION_ADAPTER_IDS.filter((adapterId) => connected.has(adapterId));
  const selectedAdapterId = priority.find((adapterId) => connected.has(adapterId));
  if (!selectedAdapterId) {
    return {
      adapterId: input.defaultAdapterId,
      fallbackAdapterIds: [],
      reason: "default_no_connected_task_adapters",
      codeLike,
      taskKind,
      connectedAdapterIds,
    };
  }
  return {
    adapterId: selectedAdapterId,
    fallbackAdapterIds: priority.filter((adapterId) => adapterId !== selectedAdapterId && connected.has(adapterId)),
    reason: `${taskKind}_task_${selectedAdapterId}`,
    codeLike,
    taskKind,
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

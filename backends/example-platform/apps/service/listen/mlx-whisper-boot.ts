// domain-pending(DIV-DOMCORE-012)

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const MLX_WHISPER_ENGINE = "mlx-whisper";
export const DEFAULT_MLX_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo";
export const DEFAULT_STT_DIR_RELATIVE = ".local/stt";
export const DEFAULT_STT_VENV_RELATIVE = ".local/stt/venv";
export const STT_BOOTSTRAP_SCRIPT = "scripts/stt-bootstrap.sh";
export const STT_BOOTSTRAP_STAMP_NAME = "bootstrap.json";
export const STT_BOOTSTRAP_STAMP_SCHEMA = "omi.stt-bootstrap.v1";

export const MLX_WHISPER_WORKER_PATH = join(import.meta.dir, "mlx-whisper-worker.py");
export const MLX_WHISPER_WORKER_STUB_PATH = join(import.meta.dir, "mlx-whisper-worker-stub.py");

/** Fail-closed boot copy. Names the env var and the engine token; never interpolates values. */
export const MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE =
  "OMI_STT_ENGINE must be unset (scripted local STT) or mlx-whisper.";

export const MLX_WHISPER_VENV_ABSENT_MESSAGE =
  "OMI_STT_ENGINE is mlx-whisper but the on-device STT venv is absent. "
  + `Run ${STT_BOOTSTRAP_SCRIPT} then reboot the dev server.`;

export const MLX_WHISPER_MODEL_ABSENT_MESSAGE =
  "OMI_STT_ENGINE is mlx-whisper but the on-device STT model is not bootstrapped. "
  + `Run ${STT_BOOTSTRAP_SCRIPT} then reboot the dev server.`;

export const MLX_WHISPER_WORKER_ABSENT_MESSAGE =
  "OMI_STT_ENGINE is mlx-whisper but the worker script is missing from the checkout.";

export class DevSttConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DevSttConfigError";
  }
}

export interface DevSttEnv {
  readonly OMI_STT_ENGINE?: string;
  readonly OMI_STT_MODEL?: string;
  readonly OMI_STT_VENV?: string;
}

export type DevSttConfig =
  | { readonly kind: "scripted" }
  | {
    readonly kind: "mlx-whisper";
    readonly pythonPath: string;
    readonly workerPath: string;
    readonly model: string;
    readonly venvPath: string;
    readonly hfHome: string;
  };

export const serviceRepoRoot = (fromDir = import.meta.dir): string =>
  resolve(fromDir, "../../..");

const hubDirForModel = (hfHome: string, model: string): string =>
  join(hfHome, "hub", `models--${model.replaceAll("/", "--")}`);

const pythonExecutable = (venvPath: string): string => join(venvPath, "bin", "python");

const mlxWhisperIsInstalled = (venvPath: string): boolean => {
  const lib = join(venvPath, "lib");
  if (!existsSync(lib)) return false;
  return readdirSync(lib).some((entry) => (
    entry.startsWith("python")
    && existsSync(join(lib, entry, "site-packages", "mlx_whisper"))
  ));
};

const stampRecordsModel = (stampPath: string, model: string): boolean => {
  if (!existsSync(stampPath)) return false;
  try {
    const stamp = JSON.parse(readFileSync(stampPath, "utf8")) as {
      readonly schema?: unknown;
      readonly engine?: unknown;
      readonly model?: unknown;
    };
    return stamp.schema === STT_BOOTSTRAP_STAMP_SCHEMA
      && stamp.engine === MLX_WHISPER_ENGINE
      && stamp.model === model;
  } catch {
    return false;
  }
};

const modelIsPresent = (hfHome: string, stampPath: string, model: string): boolean => {
  if ((model.startsWith("/") || model.startsWith("./") || model.startsWith("../"))
    && existsSync(model)) {
    return true;
  }
  if (stampRecordsModel(stampPath, model)) return true;
  return existsSync(hubDirForModel(hfHome, model));
};

export const resolveDevSttConfig = (
  env: DevSttEnv,
  options: { readonly repoRoot: string } = { repoRoot: serviceRepoRoot() },
): DevSttConfig => {
  const engine = env.OMI_STT_ENGINE?.trim() ?? "";
  if (engine.length === 0) return Object.freeze({ kind: "scripted" as const });
  if (engine !== MLX_WHISPER_ENGINE) {
    throw new DevSttConfigError(MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE);
  }

  const repoRoot = options.repoRoot;
  const venvPath = resolve(repoRoot, env.OMI_STT_VENV?.trim() || DEFAULT_STT_VENV_RELATIVE);
  const sttDir = dirname(venvPath);
  const hfHome = join(sttDir, "hf-cache");
  const stampPath = join(sttDir, STT_BOOTSTRAP_STAMP_NAME);
  const pythonPath = pythonExecutable(venvPath);
  const model = env.OMI_STT_MODEL?.trim() || DEFAULT_MLX_WHISPER_MODEL;

  if (!existsSync(pythonPath) || !mlxWhisperIsInstalled(venvPath)) {
    throw new DevSttConfigError(MLX_WHISPER_VENV_ABSENT_MESSAGE);
  }
  if (!existsSync(MLX_WHISPER_WORKER_PATH)) {
    throw new DevSttConfigError(MLX_WHISPER_WORKER_ABSENT_MESSAGE);
  }
  if (!modelIsPresent(hfHome, stampPath, model)) {
    throw new DevSttConfigError(MLX_WHISPER_MODEL_ABSENT_MESSAGE);
  }

  return Object.freeze({
    kind: "mlx-whisper" as const,
    pythonPath,
    workerPath: MLX_WHISPER_WORKER_PATH,
    model,
    venvPath,
    hfHome,
  });
};

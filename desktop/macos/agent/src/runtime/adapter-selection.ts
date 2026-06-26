export const ADAPTER_ACTIVATION_ENV = {
  acp: undefined,
  "pi-mono": "OMI_AUTH_TOKEN",
  hermes: "OMI_HERMES_ADAPTER_COMMAND",
  openclaw: "OMI_OPENCLAW_ADAPTER_COMMAND",
} as const;

export type SelectableAdapterId = keyof typeof ADAPTER_ACTIVATION_ENV;

export function adapterIdForHarnessMode(harnessMode: string | undefined): SelectableAdapterId {
  switch (harnessMode) {
    case "piMono":
    case "pi-mono":
      return "pi-mono";
    case "hermes":
      return "hermes";
    case "openclaw":
    case "openClaw":
      return "openclaw";
    case "acp":
    default:
      return "acp";
  }
}

export function adapterActivationEnv(adapterId: SelectableAdapterId): string | undefined {
  return ADAPTER_ACTIVATION_ENV[adapterId];
}

export function adapterIsActivated(
  adapterId: SelectableAdapterId,
  env: NodeJS.ProcessEnv = process.env
): boolean {
  const activationEnv = adapterActivationEnv(adapterId);
  return activationEnv === undefined || Boolean(env[activationEnv]?.trim());
}

const E2E_ENV_KEYS = ['OMI_E2E', 'OMI_E2E_FAKE_AUTH'] as const

/**
 * Release binaries must never activate test-only hooks from their launch
 * environment. Run this before creating any BrowserWindow so renderer/preload
 * children inherit the scrubbed environment.
 */
export function scrubPackagedE2EEnvironment(
  isPackaged: boolean,
  env: NodeJS.ProcessEnv = process.env
): void {
  if (!isPackaged) return
  for (const key of E2E_ENV_KEYS) delete env[key]
}

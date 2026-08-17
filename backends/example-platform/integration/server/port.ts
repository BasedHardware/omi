export const DEFAULT_INTEGRATION_PORT = 4851;

/**
 * Resolve the live adversarial server's port. The direct service door owns the
 * fixed 4851 default; tests may explicitly request 0 for an OS-assigned
 * loopback port or a bounded user port.
 */
export function parseIntegrationPort(raw: string | undefined): number {
  if (raw === undefined) return DEFAULT_INTEGRATION_PORT;
  if (!/^(?:0|[1-9][0-9]{0,4})$/.test(raw)) {
    throw new Error("OMI_INTEGRATION_PORT must be 0 or an integer between 1024 and 65535");
  }
  const port = Number(raw);
  if (port !== 0 && (port < 1024 || port > 65535)) {
    throw new Error("OMI_INTEGRATION_PORT must be 0 or an integer between 1024 and 65535");
  }
  return port;
}

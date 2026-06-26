import { LocalSubprocessRuntimeAdapter } from "./local-subprocess.js";

export interface OpenClawRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class OpenClawRuntimeAdapter extends LocalSubprocessRuntimeAdapter {
  constructor(options: OpenClawRuntimeAdapterOptions = {}) {
    super({
      adapterId: "openclaw",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
      command: options.command,
      log: options.log,
    });
  }
}

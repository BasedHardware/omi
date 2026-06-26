import { LocalSubprocessRuntimeAdapter } from "./local-subprocess.js";

export interface HermesRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class HermesRuntimeAdapter extends LocalSubprocessRuntimeAdapter {
  constructor(options: HermesRuntimeAdapterOptions = {}) {
    super({
      adapterId: "hermes",
      envCommandName: "OMI_HERMES_ADAPTER_COMMAND",
      command: options.command,
      log: options.log,
    });
  }
}

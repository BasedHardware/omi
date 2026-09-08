import { AcpRuntimeAdapter } from "./acp.js";

export interface HermesRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class HermesRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: HermesRuntimeAdapterOptions = {}) {
    super({
      adapterId: "hermes",
      envCommandName: "OMI_HERMES_ADAPTER_COMMAND",
      command: options.command,
      log: options.log,
    });
  }
}

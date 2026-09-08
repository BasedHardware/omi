import { AcpRuntimeAdapter } from "./acp.js";

export interface OpenClawRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class OpenClawRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: OpenClawRuntimeAdapterOptions = {}) {
    super({
      adapterId: "openclaw",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
      command: options.command,
      sessionMcpServersMode: "empty",
      supportsSessionSetModel: false,
      log: options.log,
    });
  }
}

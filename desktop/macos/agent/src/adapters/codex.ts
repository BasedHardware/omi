import { AcpRuntimeAdapter } from "./acp.js";

export interface CodexRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: "codex",
      envCommandName: "OMI_CODEX_ADAPTER_COMMAND",
      command: options.command,
      log: options.log,
    });
  }
}

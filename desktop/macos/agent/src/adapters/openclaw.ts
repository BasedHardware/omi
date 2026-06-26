import { OneShotCliRuntimeAdapter } from "./one-shot-cli.js";

export interface OpenClawRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class OpenClawRuntimeAdapter extends OneShotCliRuntimeAdapter {
  constructor(options: OpenClawRuntimeAdapterOptions = {}) {
    super({
      adapterId: "openclaw",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
      command: options.command,
      promptFlag: "--message",
      log: options.log,
    });
  }
}

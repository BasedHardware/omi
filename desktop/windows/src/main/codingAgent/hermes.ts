import { AcpRuntimeAdapter } from './acp'

export interface HermesRuntimeAdapterOptions {
  command?: string
  log?: (message: string) => void
}

export class HermesRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: HermesRuntimeAdapterOptions = {}) {
    super({
      adapterId: 'hermes',
      envCommandName: 'OMI_HERMES_ADAPTER_COMMAND',
      command: options.command,
      // Hermes reads its config/state from HERMES_HOME; forward it so the
      // spawned `hermes acp` subprocess doesn't fall back to defaults.
      extraEnvPassthrough: ['HERMES_HOME'],
      log: options.log
    })
  }
}

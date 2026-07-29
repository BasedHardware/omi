import { AcpError } from "./adapters/acp.js";

type InitializeAcpWithDetachedAuthInput<T> = {
  initialize: () => Promise<T>;
  onAuthRequired: (error: AcpError) => void;
  signalAuthRequired: () => void;
  startAuthFlow: () => Promise<void>;
  reinitialize: () => Promise<void>;
  log: (message: string) => void;
};

export async function initializeAcpWithDetachedAuth<T>({
  initialize,
  onAuthRequired,
  signalAuthRequired,
  startAuthFlow,
  reinitialize,
  log,
}: InitializeAcpWithDetachedAuthInput<T>): Promise<T> {
  try {
    return await initialize();
  } catch (error) {
    if (error instanceof AcpError && error.code === -32000) {
      onAuthRequired(error);
      signalAuthRequired();
      void startAuthFlow()
        .then(reinitialize)
        .catch((authError) => log(`ACP authentication retry failed: ${authError}`));
    }
    throw error;
  }
}

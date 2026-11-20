/**
 * Owns the bridge's live ACP instance across worker retirement and shutdown.
 * Retired exits cannot invalidate its replacement; stop failures stay contained.
 */
interface ManagedAcpAdapter {
  onProcessExit?: () => void;
  stop(): Promise<void>;
}

/** Owns the bridge singleton separately from the pool's contract-checking facade. */
export class AcpAdapterOwner<T extends ManagedAcpAdapter> {
  private adapter: T;

  constructor(
    private readonly create: () => T,
    private readonly invalidate: () => void,
    private readonly log: (message: string) => void,
  ) {
    this.adapter = this.createOwnedAdapter();
  }

  get current(): T {
    return this.adapter;
  }

  private createOwnedAdapter(): T {
    const adapter = this.create();
    adapter.onProcessExit = () => {
      // A retired process can exit after its replacement has initialized.
      if (this.adapter === adapter) this.invalidate();
    };
    return adapter;
  }

  retire(): void {
    const retired = this.adapter;
    this.adapter = this.createOwnedAdapter();
    this.invalidate();
    void this.stopAdapter(retired);
  }

  /** Shutdown must continue even when bounded stop had to detach the child. */
  async stop(): Promise<void> {
    await this.stopAdapter(this.adapter);
  }

  private async stopAdapter(adapter: T): Promise<void> {
    try {
      await adapter.stop();
    } catch (error) {
      this.log(`ACP shutdown failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

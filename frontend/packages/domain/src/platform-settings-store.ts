/** Live Settings store over the platform Settings adapter. */

import type {
  DeadLetter,
  HttpClient,
  SettingsAppearancePreference,
  SettingsPatch,
  SettingsSnapshot,
} from "@omi-core/contracts";
import { isSettingsAppearanceSelection } from "@omi-core/contracts";
import {
  deletePlatformCurrentSession,
  fetchPlatformSettings,
} from "@omi-core/adapters-platform";
import type { QueueStatus } from "@omi-core/sync";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const IDLE_QUEUE: QueueStatus = { phase: "idle", pendingCount: 0 };

export class PlatformSettingsStore {
  private readonly listeners = new Set<() => void>();
  private readonly refreshTracker = new RefreshTracker(false);
  private current: SettingsSnapshot;
  /** Whether the cached service portion is safe to present after a read failure. */
  private serverSnapshotUsable = false;
  private signOutFlight: Promise<void> | null = null;

  private constructor(
    private readonly http: HttpClient,
    private readonly preference: SettingsAppearancePreference,
    appearance: SettingsSnapshot["appearance"],
  ) {
    this.current = { identity: null, entitlement: null, appearance };
  }

  static async open(
    http: HttpClient,
    preference: SettingsAppearancePreference,
  ): Promise<PlatformSettingsStore> {
    const saved = await preference.readAppearance();
    if (saved !== null && !isSettingsAppearanceSelection(saved)) {
      throw new TypeError("invalid Settings appearance preference");
    }
    return new PlatformSettingsStore(http, preference, saved ?? "default");
  }

  snapshot(): Promise<SettingsSnapshot> {
    return Promise.resolve(this.current);
  }

  status(): StoreStatus {
    return { refresh: this.refreshTracker.snapshot(), queue: IDLE_QUEUE };
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    let outcome: Awaited<ReturnType<typeof fetchPlatformSettings>>;
    try {
      outcome = await fetchPlatformSettings(this.http);
    } catch {
      outcome = { kind: "unavailable", status: 503 };
    }
    if (!this.refreshTracker.isCurrent(token)) return;

    if (outcome.kind === "snapshot") {
      await this.refreshTracker.applyIfCurrent(token, async () => {
        this.current = { ...outcome.snapshot, appearance: this.current.appearance };
        this.serverSnapshotUsable = true;
      });
      if (this.refreshTracker.isCurrent(token)) {
        this.refreshTracker.complete(token, true, true);
      }
    } else {
      if (outcome.kind === "auth-invalid") this.serverSnapshotUsable = false;
      this.refreshTracker.complete(token, false, this.serverSnapshotUsable);
    }
    this.notify();
  }

  async patch(patch: SettingsPatch): Promise<void> {
    if (!Object.hasOwn(patch, "appearance") || patch.appearance === undefined) return;
    if (!isSettingsAppearanceSelection(patch.appearance)) {
      throw new TypeError("invalid Settings appearance patch");
    }
    if (patch.appearance === this.current.appearance) return;
    await this.preference.writeAppearance(patch.appearance);
    this.current = { ...this.current, appearance: patch.appearance };
    this.notify();
  }

  signOut(): Promise<void> {
    if (this.serverSnapshotUsable && this.current.identity === null) return Promise.resolve();
    if (this.signOutFlight !== null) return this.signOutFlight;
    const flight = this.performSignOut().finally(() => {
      if (this.signOutFlight === flight) this.signOutFlight = null;
    });
    this.signOutFlight = flight;
    return flight;
  }

  deadLetters(): Promise<DeadLetter[]> {
    return Promise.resolve([]);
  }

  discardDeadLetter(_opId: string): Promise<void> {
    return Promise.resolve();
  }

  private async performSignOut(): Promise<void> {
    const outcome = await deletePlatformCurrentSession(this.http);
    if (!outcome.ok) throw new Error(`Settings sign-out unavailable (${outcome.status})`);
    const token = this.refreshTracker.begin();
    this.current = {
      identity: null,
      entitlement: null,
      appearance: this.current.appearance,
    };
    this.serverSnapshotUsable = true;
    this.refreshTracker.complete(token, true, true);
    this.notify();
  }

  private notify(): void {
    for (const listener of this.listeners) listener();
  }
}

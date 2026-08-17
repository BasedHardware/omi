import type { StoreStatus } from "@omi-core/domain";
import type {
  PlatformScreenBridgeAccess,
  PlatformScreenCaptureEngineState,
  PlatformScreenFrameImage,
  PlatformScreenPermissionState,
  PlatformScreenStatus,
  ScreenDaySpanSummary,
  ScreenFrameRef,
  ScreenOcrAttachment,
  ScreenRetentionDays,
  ScreenTextSearchHit,
  ScreenTimelineFrame,
} from "@omi-core/adapters-platform";
import type { ScreenEmptyKind, ScreenPlaybackRate, ScreenSearchGroup } from "./screen-presentation.js";

export type ScreenFrameImageState =
  | { readonly kind: "absent" }
  | { readonly kind: "loading" }
  | { readonly kind: "unavailable" }
  | { readonly kind: "ready"; readonly image: PlatformScreenFrameImage };

export type ScreenCaptureTone = "green" | "red" | "amber";

/**
 * Surface-facing composition boundary for Rewind / screen history.
 *
 * Status / subscribe / refresh match the other production stores so the
 * component can reuse the exemplar lifecycle. Capture control, day selection,
 * search, playback, retention, and exclusions live here so the surface never
 * fetches inline.
 */
export type ProductionScreenStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  days(): ScreenDaySpanSummary;
  selectedDay(): string | null;
  selectDay(day: string): Promise<void>;
  jumpDay(direction: "older" | "newer" | "oldest"): Promise<void>;
  timeline(): readonly ScreenTimelineFrame[];
  frameCursor(): number;
  selectedFrame(): ScreenTimelineFrame | null;
  selectFrame(index: number): void;
  stepFrame(delta: number): void;
  searchQuery(): string;
  setSearchQuery(query: string): void;
  searchHits(): readonly ScreenTextSearchHit[];
  searchGroups(): readonly ScreenSearchGroup[];
  selectedGroupIndex(): number;
  selectSearchGroup(index: number): Promise<void>;
  stepSearchGroup(delta: number): Promise<void>;
  matchedBlockIds(): readonly string[];
  ocrForSelectedFrame(): ScreenOcrAttachment | null;
  frameImage(): ScreenFrameImageState;
  playbackRate(): ScreenPlaybackRate;
  setPlaybackRate(rate: ScreenPlaybackRate): void;
  playing(): boolean;
  play(): void;
  pause(): void;
  unwind(): void;
  emptyKind(): ScreenEmptyKind | null;
  captureStatus(): PlatformScreenStatus | null;
  captureTone(): ScreenCaptureTone;
  bridgeAvailable(): boolean;
  captureEverEnabled(): boolean;
  startCapture(): Promise<void>;
  stopCapture(): Promise<void>;
  requestPermission(): Promise<void>;
  openSettings(): Promise<void>;
  rebuildIndex(): Promise<{ frames: number; chunks: number } | null>;
  retentionDays(): ScreenRetentionDays;
  setRetentionDays(days: ScreenRetentionDays): Promise<void>;
  exclusions(): readonly string[];
  setExclusions(bundleIds: readonly string[]): Promise<void>;
  addExclusion(bundleId: string): Promise<void>;
  removeExclusion(bundleId: string): Promise<void>;
  resetExclusions(): Promise<void>;
  framesStored(): number;
  bytesOnDisk(): number | null;
  openFrame(frameId: string): Promise<boolean>;
  selectedFrameRef(): ScreenFrameRef | null;
  engineState(): PlatformScreenCaptureEngineState | null;
  permission(): PlatformScreenPermissionState | null;
  bridge(): PlatformScreenBridgeAccess;
};

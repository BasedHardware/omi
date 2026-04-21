import type { ReactNode } from "react";
import { useAuthStore } from "../../stores/authStore";
import { useDevStore } from "../../stores/devStore";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useOnboardingCompanionStore } from "../../stores/onboardingCompanionStore";
import { Switch } from "../ui/switch";
import { PttDebugPanel } from "./PttDebugPanel";

function SettingsSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="settings-section">
      <h3 className="settings-section-title">{title}</h3>
      <div className="settings-section-content">{children}</div>
    </div>
  );
}

export function SettingsPage() {
  const { userEmail, userId, signOut } = useAuthStore();
  const {
    developerMode,
    memoryIndicatorEnabled,
    bypassCommercialHours,
    liveTranscriptWindowEnabled,
    toggleDeveloperMode,
    toggleMemoryIndicator,
    toggleBypassCommercialHours,
    toggleLiveTranscriptWindow,
  } = useDevStore();

  return (
    <div className="settings-page">
      <div className="page-header">
        <h2>Settings</h2>
      </div>
      <div className="settings-content">
        <SettingsSection title="Account">
          <div className="settings-row">
            <span className="settings-label">Email</span>
            <span className="settings-value">{userEmail || "Not signed in"}</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">User ID</span>
            <span className="settings-value settings-value-mono">
              {userId || "N/A"}
            </span>
          </div>
          <div className="settings-row">
            <button onClick={signOut} className="settings-button-danger">
              Sign Out
            </button>
          </div>
          <div className="settings-row">
            <div className="flex flex-col gap-0.5">
              <span className="settings-label">Replay onboarding</span>
              <span className="text-[11px] text-muted-foreground/70">
                Clear local onboarding state and return to step 1.
              </span>
            </div>
            <button
              onClick={() => {
                useOnboardingStore.getState().resetOnboarding();
                useOnboardingCompanionStore.getState().reset();
              }}
              className="settings-button-danger"
            >
              Reset
            </button>
          </div>
        </SettingsSection>

        <SettingsSection title="Audio">
          <div className="settings-placeholder">
            Audio input/output settings will be available in a future update.
          </div>
        </SettingsSection>

        <SettingsSection title="Rewind">
          <div className="settings-placeholder">
            Screen rewind and recall settings will be available in a future update.
          </div>
        </SettingsSection>

        <SettingsSection title="Shortcuts">
          <div className="settings-placeholder">
            Keyboard shortcut configuration will be available in a future update.
          </div>
        </SettingsSection>

        <SettingsSection title="Notifications">
          <div className="settings-placeholder">
            Notification preferences will be available in a future update.
          </div>
        </SettingsSection>

        <SettingsSection title="Developer">
          <div className="settings-row">
            <div className="flex flex-col gap-0.5">
              <span className="settings-label">Developer mode</span>
              <span className="text-[11px] text-muted-foreground/70">
                Expose experimental diagnostics and tools.
              </span>
            </div>
            <Switch
              checked={developerMode}
              onCheckedChange={toggleDeveloperMode}
              aria-label="Developer mode"
            />
          </div>
          {developerMode && (
            <div className="settings-row">
              <div className="flex flex-col gap-0.5">
                <span className="settings-label">Memory usage indicator</span>
                <span className="text-[11px] text-muted-foreground/70">
                  Show a floating badge with current process / system memory.
                </span>
              </div>
              <Switch
                checked={memoryIndicatorEnabled}
                onCheckedChange={toggleMemoryIndicator}
                aria-label="Memory usage indicator"
              />
            </div>
          )}
          {developerMode && (
            <div className="settings-row">
              <div className="flex flex-col gap-0.5">
                <span className="settings-label">Bypass working hours</span>
                <span className="text-[11px] text-muted-foreground/70">
                  Allow Rewind and audio capture to run outside Mon–Fri 9am–5pm.
                </span>
              </div>
              <Switch
                checked={bypassCommercialHours}
                onCheckedChange={toggleBypassCommercialHours}
                aria-label="Bypass working hours"
              />
            </div>
          )}
          {developerMode && (
            <div className="settings-row">
              <div className="flex flex-col gap-0.5">
                <span className="settings-label">Live transcript window</span>
                <span className="text-[11px] text-muted-foreground/70">
                  Show the floating live-transcript overlay during meetings.
                </span>
              </div>
              <Switch
                checked={liveTranscriptWindowEnabled}
                onCheckedChange={toggleLiveTranscriptWindow}
                aria-label="Live transcript window"
              />
            </div>
          )}
          {developerMode && <PttDebugPanel />}
        </SettingsSection>

        <SettingsSection title="About">
          <div className="settings-row">
            <span className="settings-label">App</span>
            <span className="settings-value">Nooto Desktop</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">Version</span>
            <span className="settings-value">0.1.0</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">Platform</span>
            <span className="settings-value">Tauri 2.0</span>
          </div>
        </SettingsSection>
      </div>
    </div>
  );
}

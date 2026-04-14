/**
 * FocusIndicator — compact sidebar/header component that shows the current
 * focus status and lets the user toggle monitoring on/off.
 *
 * Status dot colors:
 *   green  — focused
 *   red    — distracted
 *   gray   — inactive / no analysis yet
 */

import { useFocusStore } from "@/stores/focusStore";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface StatusDotProps {
  status: "focused" | "distracted" | "inactive";
  isAnalyzing: boolean;
}

function StatusDot({ status, isAnalyzing }: StatusDotProps) {
  const colorMap = {
    focused: "#22c55e",    // green-500
    distracted: "#ef4444", // red-500
    inactive: "#6b7280",   // gray-500
  };

  const color = colorMap[status];

  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        animation: isAnalyzing ? "focus-pulse 1s ease-in-out infinite" : undefined,
        boxShadow: status !== "inactive" ? `0 0 0 0 ${color}` : undefined,
      }}
      title={isAnalyzing ? "Analyzing..." : status}
    />
  );
}

// ---------------------------------------------------------------------------
// Toggle switch
// ---------------------------------------------------------------------------

interface ToggleProps {
  checked: boolean;
  onChange: () => void;
  label: string;
}

function Toggle({ checked, onChange, label }: ToggleProps) {
  return (
    <button
      onClick={onChange}
      role="switch"
      aria-checked={checked}
      title={label}
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        width: 32,
        height: 18,
        borderRadius: 9,
        background: checked ? "var(--app-accent)" : "var(--bg-tertiary)",
        border: "none",
        cursor: "pointer",
        padding: 0,
        transition: "background 0.2s",
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: "absolute",
          left: checked ? 16 : 2,
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: "white",
          transition: "left 0.2s",
          boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        }}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function FocusIndicator() {
  const {
    focusEnabled,
    currentStatus,
    lastAnalysis,
    isAnalyzing,
    notificationsEnabled,
    toggleFocus,
    toggleNotifications,
  } = useFocusStore();

  const dotStatus =
    !focusEnabled || currentStatus === null
      ? "inactive"
      : currentStatus;

  return (
    <>
      {/* Keyframe for pulse animation injected once */}
      <style>{`
        @keyframes focus-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: "10px 12px",
          borderRadius: 8,
          background: "var(--bg-tertiary)",
          border: "1px solid var(--app-border)",
        }}
      >
        {/* Header row: dot + label + toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusDot status={dotStatus} isAnalyzing={isAnalyzing} />
          <span
            style={{
              flex: 1,
              fontSize: 13,
              fontWeight: 500,
              color: "var(--text-primary)",
              lineHeight: 1.2,
            }}
          >
            Focus
          </span>
          <Toggle
            checked={focusEnabled}
            onChange={toggleFocus}
            label={focusEnabled ? "Stop monitoring" : "Start monitoring"}
          />
        </div>

        {/* App/site label */}
        {focusEnabled && lastAnalysis && (
          <div
            style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={lastAnalysis.app_or_site}
          >
            {lastAnalysis.app_or_site}
          </div>
        )}

        {/* Coaching message */}
        {focusEnabled && lastAnalysis?.message && (
          <div
            style={{
              fontSize: 12,
              color:
                lastAnalysis.status === "distracted"
                  ? "#ef4444"
                  : "#22c55e",
              lineHeight: 1.4,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {lastAnalysis.message}
          </div>
        )}

        {/* Inactive hint */}
        {!focusEnabled && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            Monitoring off
          </div>
        )}

        {/* Analyzing spinner text */}
        {focusEnabled && isAnalyzing && !lastAnalysis && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            Analyzing screen...
          </div>
        )}

        {/* Notifications row — only visible when monitoring is on */}
        {focusEnabled && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              paddingTop: 4,
              borderTop: "1px solid var(--app-border)",
              marginTop: 2,
            }}
          >
            <span
              style={{
                flex: 1,
                fontSize: 11,
                color: "var(--text-secondary)",
              }}
            >
              Notifications
            </span>
            <Toggle
              checked={notificationsEnabled}
              onChange={toggleNotifications}
              label={notificationsEnabled ? "Disable notifications" : "Enable notifications"}
            />
          </div>
        )}
      </div>
    </>
  );
}

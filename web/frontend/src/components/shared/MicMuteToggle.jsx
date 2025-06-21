import React, { useEffect, useState, useRef } from "react";

// Mic On/Off Icons (Heroicons style, strikethrough for muted)
const MicOnIcon = ({ color = "#fff" }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <path d="M12 19v2m0 0h-4m4 0h4M19 10a7 7 0 01-14 0m7 4a3 3 0 003-3V6a3 3 0 10-6 0v5a3 3 0 003 3z"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transition: 'stroke 0.2s' }}
    />
  </svg>
);

const MicOffIcon = ({ color = "#fff" }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <path d="M19 10a7 7 0 01-7 7m0 0a7 7 0 01-7-7M12 17v4m0 0h4m-4 0H8m8-4V6a3 3 0 10-6 0v6"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transition: 'stroke 0.2s' }}
    />
    <line
      x1="5"
      y1="5"
      x2="19"
      y2="19"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      style={{ transition: 'stroke 0.2s' }}
    />
  </svg>
);

const STORAGE_KEY = "mic-muted-until";
function getRemainingMuteMs() {
  const until = localStorage.getItem(STORAGE_KEY);
  if (!until) return 0;
  const ms = parseInt(until, 10) - Date.now();
  return ms > 0 ? ms : 0;
}

export default function MicMuteToggle({ stream }) {
  const [muted, setMuted] = useState(getRemainingMuteMs() > 0);
  const [showMenu, setShowMenu] = useState(false);
  const [remaining, setRemaining] = useState(getRemainingMuteMs());
  const timerRef = useRef();
  const menuRef = useRef();

  // Timer for auto-unmute
  useEffect(() => {
    if (muted && remaining > 0) {
      timerRef.current = setInterval(() => {
        const ms = getRemainingMuteMs();
        setRemaining(ms);
        if (ms === 0) {
          setMuted(false);
          localStorage.removeItem(STORAGE_KEY);
          stream?.getAudioTracks().forEach(track => (track.enabled = true));
        }
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [muted, remaining, stream]);

  // Apply mute/unmute to stream
  useEffect(() => {
    if (stream) {
      stream.getAudioTracks().forEach(track => (track.enabled = !muted));
    }
  }, [muted, stream]);

  // Restore mute state on mount
  useEffect(() => {
    if (getRemainingMuteMs() > 0) {
      setMuted(true);
      setRemaining(getRemainingMuteMs());
    }
  }, []);

  // Click-outside-to-close for menu
  useEffect(() => {
    if (!showMenu) return;
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("touchstart", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, [showMenu]);

  function handleToggle() {
    if (muted) {
      setMuted(false);
      localStorage.removeItem(STORAGE_KEY);
      setRemaining(0);
    } else {
      setShowMenu(true);
    }
  }

  function handleSetMute(durationMs) {
    setMuted(true);
    const until = Date.now() + durationMs;
    localStorage.setItem(STORAGE_KEY, until.toString());
    setRemaining(durationMs);
    setShowMenu(false);
  }

  function formatTime(ms) {
    const totalSec = Math.ceil(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, "0")}`;
  }

  // Button gradient colors
  const BUTTON_GRADIENT = "linear-gradient(to right, #2563eb, #9333ea)";
  const BUTTON_GRADIENT_HOVER = "linear-gradient(to right, #1d4ed8, #7e22ce)";

  return (
    <div style={{ position: "relative", marginLeft: 12 }}>
      {/* BUTTON */}
      <button
        onClick={handleToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "8px 18px",
          borderRadius: "0.5rem",
          background: BUTTON_GRADIENT,
          color: "#fff",
          border: "none",
          cursor: "pointer",
          fontWeight: 600,
          fontSize: 15,
          boxShadow: "0 2px 8px #0002",
          transition: "background 0.2s, box-shadow 0.2s, transform 0.2s, color 0.2s",
          outline: "none"
        }}
        onMouseEnter={e => e.currentTarget.style.background = BUTTON_GRADIENT_HOVER}
        onMouseLeave={e => e.currentTarget.style.background = BUTTON_GRADIENT}
        aria-label={muted ? "Unmute microphone" : "Mute microphone"}
        title={muted ? "Unmute microphone" : "Mute microphone"}
      >
        {muted ? <MicOffIcon color="#fff" /> : <MicOnIcon color="#fff" />}
        <span
          style={{
            marginLeft: 3,
            fontWeight: 600,
            fontSize: 15,
            color: "#fff",
            transition: "color 0.2s"
          }}
        >
          {muted ? "Muted" : "On"}
        </span>
        {muted && remaining > 0
          ? <span style={{ marginLeft: 5, fontWeight: 400, fontSize: 13, color: "#e0e7ef" }}>({formatTime(remaining)})</span>
          : null}
      </button>
      {/* MENU */}
      {showMenu && (
        <div
          ref={menuRef}
          style={{
            position: "absolute",
            top: 48,
            right: 0,
            minWidth: 160,
            background: "#181e29",
            border: "1px solid #22223b",
            borderRadius: "0.75rem",
            zIndex: 10,
            boxShadow: "0 4px 18px #0004",
            color: "#fff",
            padding: 4,
            transition: "background 0.2s"
          }}>
          <div style={{
            padding: "12px 14px 10px 14px",
            fontWeight: 600,
            fontSize: 15,
            color: "#cbd5e1",
            userSelect: "none"
          }}>Mute mic for:</div>
          <MenuButton onClick={() => handleSetMute(30 * 60 * 1000)} label="30 minutes" />
          <MenuButton onClick={() => handleSetMute(60 * 60 * 1000)} label="1 hour" />
          <MenuButton onClick={() => handleSetMute(2 * 60 * 60 * 1000)} label="2 hours" />
          <MenuButton onClick={() => setShowMenu(false)} label="Cancel" muted />
        </div>
      )}
    </div>
  );
}

// MenuButton uses gradient on hover
function MenuButton({ onClick, label, muted }) {
  const GRAD = "linear-gradient(to right, #2563eb, #9333ea)";
  const GRAD_HOVER = "linear-gradient(to right, #1d4ed8, #7e22ce)";
  const [hover, setHover] = useState(false);

  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        padding: "10px 16px",
        textAlign: "left",
        background: hover && !muted ? GRAD_HOVER : "none",
        border: "none",
        cursor: "pointer",
        color: muted ? "#b0b6c5" : "#fff",
        fontSize: 15,
        borderRadius: "0.5rem",
        marginBottom: 2,
        fontWeight: 500,
        transition: "background 0.15s, color 0.15s"
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      aria-label={label}
    >
      {label}
    </button>
  );
}
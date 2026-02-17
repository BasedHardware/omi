import React from "react";

export const SlackIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 128 128">
    <path d="M26.9 80.4a13.4 13.4 0 1 1-13.4-13.4h13.4v13.4z" fill="#E01E5A" />
    <path d="M33.6 80.4a13.4 13.4 0 0 1 26.8 0v33.5a13.4 13.4 0 1 1-26.8 0V80.4z" fill="#E01E5A" />
    <path d="M47 26.9a13.4 13.4 0 1 1 13.4-13.4v13.4H47z" fill="#36C5F0" />
    <path d="M47 33.6a13.4 13.4 0 0 1 0 26.8H13.4a13.4 13.4 0 0 1 0-26.8H47z" fill="#36C5F0" />
    <path d="M100.6 47a13.4 13.4 0 1 1 13.4 13.4h-13.4V47z" fill="#2EB67D" />
    <path d="M93.9 47a13.4 13.4 0 0 1-26.8 0V13.4a13.4 13.4 0 0 1 26.8 0V47z" fill="#2EB67D" />
    <path d="M80.5 100.6a13.4 13.4 0 1 1-13.4 13.4v-13.4h13.4z" fill="#ECB22E" />
    <path d="M80.5 93.9a13.4 13.4 0 0 1 0-26.8h33.5a13.4 13.4 0 0 1 0 26.8H80.5z" fill="#ECB22E" />
  </svg>
);

export const VSCodeIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <mask id="vsc-mask">
      <rect width="100" height="100" fill="white" />
    </mask>
    <path d="M71.6 99.1l24.7-12.3a5.4 5.4 0 0 0 3-4.9V18.1a5.4 5.4 0 0 0-3-4.9L71.5.9a5.4 5.4 0 0 0-6.2 1.1L27.7 37.6 11.5 25.1a3.6 3.6 0 0 0-4.6.3L1.2 31a3.6 3.6 0 0 0 0 5.3L15.5 50 1.2 63.7a3.6 3.6 0 0 0 0 5.3l5.7 5.6a3.6 3.6 0 0 0 4.6.3L27.7 62.4l37.6 35.6a5.4 5.4 0 0 0 6.3 1.1zM71.6 27L42 50l29.6 23V27z" fill="#007ACC" />
  </svg>
);

export const NotionIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
    <path d="M6.017 4.313l55.333-4.087c6.797-.583 8.543-.19 12.817 2.917l17.663 12.443c2.913 2.14 3.883 2.723 3.883 5.053v68.243c0 4.277-1.553 6.807-6.99 7.193L24.467 99.967c-4.08.193-6.023-.39-8.16-3.113L3.3 79.94c-2.333-3.113-3.3-5.443-3.3-8.167V11.113c0-3.497 1.553-6.413 6.017-6.8z" fill="#fff" />
    <path fillRule="evenodd" clipRule="evenodd" d="M61.35.227l-55.333 4.087C1.553 4.7 0 7.617 0 11.113v60.66c0 2.723.967 5.053 3.3 8.167l13.007 16.913c2.137 2.723 4.08 3.307 8.16 3.113l64.257-3.89c5.433-.387 6.99-2.917 6.99-7.193V20.64c0-2.21-.856-2.864-3.53-4.78l-.353-.273-17.663-12.443C70.04.04 68.293-.357 61.497.04L61.35.227zM25.5 19.32c-5.2.33-6.38.41-9.34-1.83l-7.49-5.86c-.78-.78-.39-1.75 1.36-1.95l51.86-3.69c4.47-.39 6.8 1.17 8.54 2.53l8.16 5.86c.39.19.97 1.36 0 1.36l-53.67 3.19-.42.39zm-6.41 73.77V31.2c0-2.53.78-3.7 3.11-3.89l58.08-3.31c2.14-.19 3.11 1.17 3.11 3.7v61.5c0 2.53-1.56 5.06-4.86 5.25l-55.54 3.11c-3.31.19-3.89-1.75-3.89-3.5zm54.77-59.36c.39 1.75 0 3.5-1.75 3.7l-2.72.58v45.5c-2.33 1.17-4.47 1.95-6.22 1.95-2.92 0-3.7-.97-5.83-3.5l-17.86-28.08v27.11l5.64 1.36s0 3.5-4.86 3.5l-13.39.78c-.39-.78 0-2.72 1.36-3.11l3.5-.97V40.55l-4.86-.39c-.39-1.75.58-4.28 3.3-4.47L40.68 35l18.64 28.47V38.02l-4.67-.58c-.39-2.14 1.17-3.7 3.11-3.89l13.58-.78z" fill="#000" />
  </svg>
);

export const CalendarIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <path d="M36 6h-2V2h-4v4H18V2h-4v4h-2C9.8 6 8 7.8 8 10v28c0 2.2 1.8 4 4 4h24c2.2 0 4-1.8 4-4V10c0-2.2-1.8-4-4-4zm0 32H12V16h24v22z" fill="#4285F4" />
    <rect x="16" y="20" width="6" height="6" fill="#4285F4" rx="1" />
    <rect x="26" y="20" width="6" height="6" fill="#4285F4" rx="1" />
    <rect x="16" y="30" width="6" height="6" fill="#4285F4" rx="1" />
  </svg>
);

export const ZoomIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <rect width="48" height="48" rx="8" fill="#2D8CFF" />
    <path d="M11 17a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v14a3 3 0 0 1-3 3H14a3 3 0 0 1-3-3V17z" fill="white" />
    <path d="M31 19.5l5.5-4v17l-5.5-4v-9z" fill="white" />
  </svg>
);

export const LinearIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <rect width="100" height="100" rx="20" fill="#5E6AD2" />
    <path d="M19.2 68.8a40 40 0 0 0 12 12l36.4-36.4a3 3 0 0 0 0-4.2 3 3 0 0 0-4.2 0L19.2 68.8zm-3.3 3.3c-.4.4-.4 1 0 1.4a40 40 0 0 0 10.5 10.5c.4.4 1 .4 1.4 0L67.6 44.2a3 3 0 0 0 0-4.2 3 3 0 0 0-4.2 0L15.9 72.1z" fill="white" fillOpacity="0.9" />
    <circle cx="50" cy="50" r="20" fill="none" stroke="white" strokeWidth="5" strokeOpacity="0.9" />
  </svg>
);

export const GitHubIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 98 96">
    <path fillRule="evenodd" clipRule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z" fill="#fff" />
  </svg>
);

export const GmailIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <path d="M6 12l18 12 18-12v24a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V12z" fill="#EA4335" />
    <path d="M42 12L24 24 6 12V8a2 2 0 0 1 2-2h32a2 2 0 0 1 2 2v4z" fill="#FBBC04" />
    <path d="M6 12l18 12" stroke="#34A853" strokeWidth="2" fill="none" />
    <path d="M42 12L24 24" stroke="#4285F4" strokeWidth="2" fill="none" />
    <rect x="6" y="6" width="36" height="32" rx="2" fill="none" stroke="#EA4335" strokeWidth="3" />
    <path d="M6 10l18 14L42 10" fill="none" stroke="white" strokeWidth="3" strokeLinejoin="round" />
  </svg>
);

export const GoogleDocsIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <path d="M29 4H14a4 4 0 0 0-4 4v32a4 4 0 0 0 4 4h20a4 4 0 0 0 4-4V13L29 4z" fill="#4285F4" />
    <path d="M29 4v9h9L29 4z" fill="#A1C2FA" />
    <rect x="16" y="22" width="16" height="2" rx="1" fill="white" />
    <rect x="16" y="27" width="12" height="2" rx="1" fill="white" />
    <rect x="16" y="32" width="14" height="2" rx="1" fill="white" />
  </svg>
);

export const OmiIcon: React.FC<{ size?: number }> = ({ size = 32 }) => (
  <img
    src="/public/omi-logo.png"
    width={size}
    height={size}
    style={{ borderRadius: size * 0.2, objectFit: "contain" }}
  />
);

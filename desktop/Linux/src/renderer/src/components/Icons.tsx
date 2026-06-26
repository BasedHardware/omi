import React from 'react'

// Inline stroke icons approximating the SF Symbols the Mac sidebar uses.

interface IconProps {
  size?: number
  className?: string
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const
})

export const IconDashboard = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="3" y="3" width="7.5" height="7.5" rx="2" />
    <rect x="13.5" y="3" width="7.5" height="7.5" rx="2" />
    <rect x="3" y="13.5" width="7.5" height="7.5" rx="2" />
    <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
  </svg>
)

export const IconConversations = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M21 11.5a8.38 8.38 0 0 1-9 8.35 8.5 8.5 0 0 1-3.4-.7L3 21l1.85-5.55A8.38 8.38 0 0 1 12 3a8.5 8.5 0 0 1 9 8.5z" />
  </svg>
)

export const IconMemories = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="M18.5 15.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" />
  </svg>
)

export const IconTasks = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8.5 12.2l2.4 2.4 4.6-5" />
  </svg>
)

export const IconRewind = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 12a9 9 0 1 0 3-6.7" />
    <path d="M3 4v4h4" />
    <path d="M12 7v5l3.5 2" />
  </svg>
)

export const IconGoals = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </svg>
)

export const IconFocus = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

export const IconGraph = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="6" cy="7" r="2.4" />
    <circle cx="18" cy="6" r="2.4" />
    <circle cx="17" cy="17" r="2.4" />
    <circle cx="7.5" cy="17.5" r="2.4" />
    <path d="M8.2 7.6l7.5-1M8 9l8 6.5M16 8l-7.7 8" />
  </svg>
)

export const IconInsights = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M9 18h6" />
    <path d="M10 21h4" />
    <path d="M12 3a6 6 0 0 0-3.5 10.9c.5.4.8.9.9 1.5l.1.6h5l.1-.6c.1-.6.4-1.1.9-1.5A6 6 0 0 0 12 3z" />
  </svg>
)

export const IconApps = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 2l3 3-3 3-3-3z" />
    <path d="M19 9l3 3-3 3-3-3z" />
    <path d="M5 9l3 3-3 3-3-3z" />
    <path d="M12 16l3 3-3 3-3-3z" />
  </svg>
)

export const IconSettings = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="3.2" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z" />
  </svg>
)

export const IconHelp = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.2 9a2.9 2.9 0 0 1 5.6 1c0 1.8-2.8 2.3-2.8 4" />
    <circle cx="12" cy="17.6" r="0.4" fill="currentColor" stroke="none" />
  </svg>
)

export const IconSearch = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.5-4.5" />
  </svg>
)

export const IconMic = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="9" y="2.5" width="6" height="11" rx="3" />
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
    <path d="M12 17.5V21" />
  </svg>
)

export const IconStop = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" fill="currentColor" stroke="none" />
  </svg>
)

export const IconStar = ({ size = 15, className, filled }: IconProps & { filled?: boolean }) => (
  <svg {...base(size)} className={className} fill={filled ? 'currentColor' : 'none'}>
    <path d="M12 2.8l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4L12 17.6l-5.8 3 1.1-6.4L2.6 9.6l6.5-.9z" />
  </svg>
)

export const IconTrash = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 7h16" />
    <path d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2" />
    <path d="M6.5 7l.8 12a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9l.8-12" />
  </svg>
)

export const IconPlus = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 5v14M5 12h14" />
  </svg>
)

export const IconSend = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M22 2L11 13" />
    <path d="M22 2l-7 20-4-9-9-4z" />
  </svg>
)

export const IconCamera = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="2.5" y="6.5" width="19" height="13" rx="3" />
    <path d="M8 6.5L9.7 4h4.6L16 6.5" />
    <circle cx="12" cy="12.6" r="3.4" />
  </svg>
)

export const IconClose = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export const IconChevronLeft = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M14.5 5l-6.5 7 6.5 7" />
  </svg>
)

export const IconSidebar = ({ size = 17, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <path d="M9.5 4v16" />
  </svg>
)

export const IconExternal = ({ size = 13, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M14 4h6v6" />
    <path d="M20 4L10 14" />
    <path d="M19 13v6a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 19V6.5A1.5 1.5 0 0 1 5.5 5H11" />
  </svg>
)

export const IconPhone = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2 4.2 2 2 0 0 1 4 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8 9.6a16 16 0 0 0 6 6l1.2-1.1a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z" />
  </svg>
)

export const IconKey = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="8" cy="14" r="4.5" />
    <path d="M11.5 10.5L20 2.5" />
    <path d="M16.5 6l3 3" />
  </svg>
)

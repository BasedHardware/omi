import type { Config } from 'tailwindcss'

export default {
  content: ['./src/renderer/index.html', './src/renderer/src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Background ramp — ported from macOS OmiColors (neutral hues).
        bg: {
          primary: '#0f0f0f',
          secondary: '#1a1a1a',
          tertiary: '#252525',
          quaternary: '#343438',
          raised: '#1f1f22'
        },
        // 4-tier text hierarchy (macOS values).
        text: {
          primary: '#ffffff',
          secondary: '#e5e5e5',
          tertiary: '#b0b0b0',
          quaternary: '#888888'
        },
        // Hairlines.
        line: {
          DEFAULT: 'rgba(255, 255, 255, 0.09)',
          strong: 'rgba(255, 255, 255, 0.16)'
        },
        // Status (macOS values).
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#3b82f6',
        // Mac-parity palette (INV-UI-1 Windows carve-out, ruling B 2026-07-14).
        // Purple ports as-is from macOS OmiColors; NEW named tokens for
        // Hub/chat/brain-graph surfaces — not consumed yet, --accent stays white.
        purple: {
          primary: '#8b5cf6',
          secondary: '#a855f7',
          accent: '#7c3aed',
          light: '#d946ef'
        },
        userBubble: '#43389f',
        // Transcript speaker-bubble backgrounds (6-color dark set).
        speaker: {
          1: '#2d3748',
          2: '#1e3a5f',
          3: '#2d4a3e',
          4: '#4a3728',
          5: '#3d2e4a',
          6: '#4a3a2d'
        },
        // HomePalette — redesigned-Home (Hub) surface tokens (macOS DashboardPage).
        home: {
          paper: '#050506',
          panel: '#0c0c0d',
          tile: '#141416',
          tileHover: '#1d1a24',
          ink: '#f0ebe3',
          secondary: '#c7c3b9',
          muted: '#7d786e',
          faint: '#5c5954',
          hairline: '#27272c',
          green: '#2bc761',
          stageGlow: '#7a4df2'
        }
      },
      // Radius scale — macOS OmiChrome (window/card/section/control/chip).
      borderRadius: {
        window: '26px',
        card: '24px',
        section: '20px',
        control: '16px',
        chip: '14px'
      },
      fontFamily: {
        // Both roles resolve through --font-app (Inter Variable, with the
        // Segoe fallback stack) so the A/B hook + any future retheme is one var.
        display: ['var(--font-app)', 'sans-serif'],
        body: ['var(--font-app)', 'sans-serif'],
        // Monospace — JetBrains Mono Variable via --font-code (previously the
        // `font-mono` utility fell through to Tailwind's default → Consolas).
        mono: ['var(--font-code)', 'monospace']
      },
      backdropBlur: {
        glass: '24px',
        'glass-lg': '48px'
      },
      boxShadow: {
        glass: '0 8px 32px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
        'glass-hover': '0 12px 40px rgba(0, 0, 0, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.14)'
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' }
        },
        pulseRing: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.4' },
          '50%': { transform: 'scale(1.12)', opacity: '0.15' }
        }
      },
      animation: {
        'fade-in': 'fadeIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 2s ease-in-out infinite',
        'pulse-ring': 'pulseRing 2s ease-in-out infinite'
      }
    }
  },
  plugins: []
} satisfies Config

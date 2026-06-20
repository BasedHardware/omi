import type { Config } from 'tailwindcss'

export default {
  content: ['./src/renderer/index.html', './src/renderer/src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: 'transparent',
          secondary: 'transparent',
          tertiary: 'transparent',
          quaternary: 'transparent',
          color: 'transparent'
        },
        text: {
          primary: 'rgba(255, 255, 255, 0.95)',
          secondary: 'rgba(255, 255, 255, 0.72)',
          tertiary: 'rgba(255, 255, 255, 0.48)',
          quaternary: 'rgba(255, 255, 255, 0.32)'
        },
        purple: {
          primary: 'rgba(255, 255, 255, 0.9)',
          secondary: 'rgba(255, 255, 255, 0.75)',
          accent: 'rgba(255, 255, 255, 0.6)',
          light: 'rgba(255, 255, 255, 0.95)'
        },
        signal: {
          record: 'rgba(255, 255, 255, 0.9)',
          recordDim: 'rgba(255, 255, 255, 0.2)'
        },
        success: 'rgba(255, 255, 255, 0.85)',
        warning: 'rgba(255, 255, 255, 0.65)',
        error: 'rgba(255, 255, 255, 0.75)',
        info: 'rgba(255, 255, 255, 0.72)'
      },
      fontFamily: {
        display: [
          '"SF Pro Display"',
          '"SF Pro Text"',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI Variable"',
          'system-ui',
          'sans-serif',
          // Emoji fallback — must be listed so Windows renders emoji glyphs
          // instead of falling back to raw UTF-8 bytes shown as â characters
          '"Segoe UI Emoji"',
          '"Apple Color Emoji"',
          '"Noto Color Emoji"'
        ],
        body: [
          '"SF Pro Display"',
          '"SF Pro Text"',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI Variable"',
          'system-ui',
          'sans-serif',
          '"Segoe UI Emoji"',
          '"Apple Color Emoji"',
          '"Noto Color Emoji"'
        ]
      },
      backdropBlur: {
        glass: '24px',
        'glass-lg': '48px'
      },
      boxShadow: {
        glass: '0 8px 32px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
        'glass-hover':
          '0 12px 40px rgba(0, 0, 0, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.14)'
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
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(32px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' }
        },
        // SwiftUI .spring(response:0.4, dampingFraction:0.72) equivalent
        springEnter: {
          '0%': { opacity: '0', transform: 'scale(0.92) translateY(8px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' }
        },
        springSlideUp: {
          '0%': { opacity: '0', transform: 'translateY(24px) scale(0.96)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' }
        },
        speakerPulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' }
        }
      },
      animation: {
        'fade-in': 'fadeIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 2s ease-in-out infinite',
        'pulse-ring': 'pulseRing 2s ease-in-out infinite',
        'slide-in-right': 'slideInRight 0.28s cubic-bezier(0.22, 1, 0.36, 1) both',
        // Spring modal entrance — matches SwiftUI spring(response:0.38, damping:0.7)
        'spring-enter': 'springEnter 0.38s cubic-bezier(0.34, 1.56, 0.64, 1) both',
        'spring-slide-up': 'springSlideUp 0.34s cubic-bezier(0.34, 1.56, 0.64, 1) both',
        'speaker-pulse': 'speakerPulse 1.4s ease-in-out infinite'
      }
    }
  },
  plugins: []
} satisfies Config

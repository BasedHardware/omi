import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    screens: {
      xs: '375px',
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
    },
    extend: {
      colors: {
        // Backgrounds
        'bg-primary': '#0F0F0F',
        'bg-secondary': '#1A1A1A',
        'bg-tertiary': '#252525',
        'bg-quaternary': '#2A2A2A',

        // Purple accent system
        'purple-primary': '#8B5CF6',
        'purple-secondary': '#A855F7',
        'purple-accent': '#7C3AED',
        'purple-light': '#D946EF',

        // Text
        'text-primary': '#FFFFFF',
        'text-secondary': '#E5E5E5',
        'text-tertiary': '#B0B0B0',
        'text-quaternary': '#888888',

        // Status
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        info: '#3B82F6',
      },
      fontFamily: {
        display: ['Plus Jakarta Sans', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
      },
      spacing: {
        'sidebar-width': '280px',
        'sidebar-collapsed': '64px',
      },
      borderRadius: {
        lg: '12px',
        md: '8px',
        sm: '6px',
      },
      boxShadow: {
        'soft': '0 4px 12px rgba(0, 0, 0, 0.1)',
        'medium': '0 8px 20px rgba(0, 0, 0, 0.15)',
        'strong': '0 12px 30px rgba(0, 0, 0, 0.25)',
        'glow': '0 0 20px rgba(139, 92, 246, 0.3)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
      animation: {
        shimmer: 'shimmer 2s infinite linear',
        fadeIn: 'fadeIn 300ms ease-out',
        slideUp: 'slideUp 300ms ease-out',
        pulse: 'pulse 2s ease-in-out infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};

export default config;

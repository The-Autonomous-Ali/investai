/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // InvestAI Design System
        surface: {
          DEFAULT: '#0C0E14',
          2:       '#13161F',
          3:       '#1A1E2A',
          4:       '#222738',
        },
        gold: {
          DEFAULT: '#D4A843',
          light:   '#F0C866',
          dark:    '#A07C28',
          muted:   '#8B6914',
        },
        jade: {
          DEFAULT: '#3DD68C',
          muted:   '#1A6B45',
        },
        ruby: {
          DEFAULT: '#E85C5C',
          muted:   '#7A2020',
        },
        ink: {
          DEFAULT: '#8892A4',
          light:   '#C2CAD8',
          dark:    '#4A5568',
        },
      },
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        body:    ['DM Sans', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'fade-in-up':    'fadeInUp 0.5s ease forwards',
        'pulse-gold':    'pulseGold 2s infinite',
        'ticker':        'ticker 30s linear infinite',
        'glow':          'glow 3s ease-in-out infinite',
      },
      keyframes: {
        fadeInUp: {
          '0%':   { opacity: 0, transform: 'translateY(20px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        pulseGold: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(212, 168, 67, 0.4)' },
          '50%':      { boxShadow: '0 0 0 8px rgba(212, 168, 67, 0)' },
        },
        glow: {
          '0%, 100%': { filter: 'drop-shadow(0 0 8px rgba(212,168,67,0.3))' },
          '50%':      { filter: 'drop-shadow(0 0 20px rgba(212,168,67,0.6))' },
        },
        ticker: {
          '0%':   { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      backdropBlur: { xs: '2px' },
    },
  },
  plugins: [],
}

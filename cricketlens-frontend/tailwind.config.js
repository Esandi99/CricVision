/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'cl-bg':       '#0a0d12',
        'cl-surface':  '#111620',
        'cl-border':   '#1e2535',
        'cl-wicket':   '#ef4444',
        'cl-nearmiss': '#f59e0b',
        'cl-text':     '#e2e8f0',
        'cl-muted':    '#4a5568',
        'cl-green':    '#22c55e',
      },
      fontFamily: {
        display: ['"Bebas Neue"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
        body:    ['Inter', 'sans-serif'],
      },
      backgroundImage: {
        scanline: "repeating-linear-gradient(to bottom, transparent, transparent 2px, rgba(255,255,255,0.02) 2px, rgba(255,255,255,0.02) 4px)",
      },
    },
  },
  plugins: [],
};

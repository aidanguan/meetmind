/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "primary": "#2c3e50",
        "primary-hover": "#1e293b",
        "accent": "#0f766e",
        "background-light": "#fdfbf7",
        "background-dark": "#1a1a1a",
        "surface-light": "#ffffff",
        "surface-dark": "#262626",
        "border-light": "#e7e5e0",
        "border-dark": "#404040",
        "text-main": "#1f2937",
        "text-muted": "#64748b",
      },
      fontFamily: {
        "display": ["'Noto Sans SC'", "Manrope", "sans-serif"],
        "sans": ["'Noto Sans SC'", "Manrope", "sans-serif"],
      },
      borderRadius: { "DEFAULT": "0.25rem", "lg": "0.375rem", "xl": "0.5rem", "full": "9999px" },
      boxShadow: {
        'soft': '0 2px 10px rgba(0, 0, 0, 0.03)',
        'card': '0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03)'
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries'),
  ],
}

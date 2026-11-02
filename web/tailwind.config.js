/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: '#FBF8F3',
        paper2: '#F2EDE3',
        ink: '#1F2937',
        muted: '#6B7280',
        teal: '#0F766E',
        tealLight: '#99D2CB',
        coral: '#E4572E',
        amber: '#D99A00',
        purple: '#7C5CBF',
        line: '#E4DED2',
      },
      fontFamily: {
        sans: ['"Inter"', 'sans-serif'],
        serif: ['"Source Serif 4"', 'serif'],
      },
    },
  },
  plugins: [],
}


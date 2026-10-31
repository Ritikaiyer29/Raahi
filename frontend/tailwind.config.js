/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { sky: { paytm: "#00BAF2" }, navy: "#002E6E", surface: "#F5F7FA" },
      fontFamily: { sans: ["Inter", "Noto Sans Devanagari", "system-ui", "sans-serif"] },
      boxShadow: { card: "0 2px 12px rgba(0,46,110,0.08)" },
      borderRadius: { card: "16px" },
    },
  },
  plugins: [],
};

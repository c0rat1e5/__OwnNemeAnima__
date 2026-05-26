/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      keyframes: {
        shimmer: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(200%)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.5s infinite",
      },
      colors: {
        // ダークテーマ用カラーパレット
        bg: {
          base:    "#0f0f0f",
          surface: "#1a1a1a",
          raised:  "#252525",
          border:  "#333333",
        },
        accent: {
          DEFAULT: "#7c3aed",  // 紫 (Anima らしい色)
          hover:   "#6d28d9",
          light:   "#8b5cf6",
        },
        text: {
          primary:   "#f0f0f0",
          secondary: "#a0a0a0",
          muted:     "#606060",
        },
      },
    },
  },
  plugins: [],
};

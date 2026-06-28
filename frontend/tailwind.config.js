/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // GHOSTWIRE palette: dark slate intelligence aesthetic
        // Primary: deep navy / gunmetal
        // Accent: electric teal
        // Danger/risk: amber → crimson
        gw: {
          bg: "#0d1117",
          surface: "#161b22",
          border: "#21262d",
          muted: "#30363d",
          text: "#e6edf3",
          subtle: "#8b949e",
          teal: "#39d0c4",
          "teal-dim": "#1a6b66",
          amber: "#d29922",
          crimson: "#da3633",
          green: "#3fb950",
        },
      },
      fontFamily: {
        sans: ["'DM Sans'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Fira Code'", "monospace"],
      },
      fontSize: {
        "2xs": ["0.65rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};

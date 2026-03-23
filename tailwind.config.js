/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html"
  ],
  theme: {
    extend: {
      animation: {
        "float-slow": "float 8s ease-in-out infinite",
        "fade-up": "fadeUp 0.65s ease-out both"
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" }
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        }
      },
      fontFamily: {
        sans: ["Satoshi", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        brand: {
          50: "#f0f8ff",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1"
        }
      }
    }
  },
  plugins: []
};

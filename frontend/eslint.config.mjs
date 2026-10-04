import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTypescript,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/ban-ts-comment": "error",
      "no-console": "error",
    },
  },
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
];

export default config;

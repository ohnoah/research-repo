import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  bundle: true,
  minify: false,
  sourcemap: true,
  shims: true,
});

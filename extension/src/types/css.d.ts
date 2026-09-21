/** esbuild's `loader: { '.css': 'text' }` (see scripts/build.mjs) turns a CSS import into its
 * raw source as a string, which content/overlay.ts injects into the shadow root via a
 * <style> tag. */
declare module '*.css' {
  const content: string;
  export default content;
}

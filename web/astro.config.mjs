// @ts-check
import preact from '@astrojs/preact';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://serverheaven.github.io',
  base: '/vpo-madrid/',
  output: 'static',
  trailingSlash: 'always',
  // Astro 7 defaults to 'jsx', which drops the space between text and an inline element on the next line.
  compressHTML: true,
  integrations: [preact()],
  vite: { plugins: [tailwindcss()] },
});

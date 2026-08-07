import { generatePackages } from '../scripts/generate-packages.mjs';

/**
 * Astro 起動時に release manifest からダウンロード一覧を生成する。
 * @returns {import('astro').AstroIntegration}
 */
export default function generatePackagesIntegration() {
  return {
    name: 'generate-packages',
    hooks: {
      'astro:config:setup': async () => {
        await generatePackages();
      },
    },
  };
}

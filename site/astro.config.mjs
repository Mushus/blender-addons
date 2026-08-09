import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';
import generatePackages from './integrations/generate-packages.mjs';

const base =
  process.env.BASE_PATH ??
  (process.env.GITHUB_ACTIONS ? '/blender-addons' : '/');

function getAddonSidebarItems() {
  const configDir = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(configDir, '..');
  const addonsDir = path.join(repoRoot, 'addons');
  let entries = [];
  try {
    entries = fs.readdirSync(addonsDir, { withFileTypes: true });
  } catch {
    return [];
  }
  const items = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const addonDir = path.join(addonsDir, entry.name);
    const addonJsonPath = path.join(addonDir, 'addon.json');
    const altJsonPath = path.join(addonDir, 'package.json');
    let jsonPath = null;
    if (fs.existsSync(addonJsonPath)) jsonPath = addonJsonPath;
    else if (fs.existsSync(altJsonPath)) jsonPath = altJsonPath;
    else continue;
    try {
      const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
      if ((data.status ?? 'stable') !== 'stable') continue;
    } catch {
      continue;
    }
    const initPath = path.join(addonDir, '__init__.py');
    let label = entry.name;
    try {
      const content = fs.readFileSync(initPath, 'utf8');
      const m = content.match(/"name"\s*:\s*"([^"]*)"/);
      if (m) label = m[1];
    } catch {
      // use directory name as fallback
    }
    const id = entry.name;
    const link = `/addons/${id.replaceAll('_', '-')}/`;
    items.push({ label, link });
  }
  // sort alphabetically by label for stable display
  items.sort((a, b) => a.label.localeCompare(b.label));
  return items;
}

// https://astro.build/config
export default defineConfig({
  site: 'https://mushus.github.io',
  base,
  integrations: [
    mermaid({
      autoTheme: true,
    }),
    generatePackages(),
    starlight({
      title: 'Blender Add-ons',
      defaultLocale: 'root',
      locales: {
        root: {
          label: '日本語',
          lang: 'ja',
        },
        en: {
          label: 'English',
          lang: 'en',
        },
      },
      social: {
        github: 'https://github.com/Mushus/blender-addons',
      },
      sidebar: [
        {
          label: 'ガイド',
          items: [
            { label: 'はじめに', link: '/guides/getting-started/' },
            { label: 'ダウンロード一覧', link: '/downloads/' },
            { label: 'インストール方法', link: '/guides/installation/' },
            {
              label: 'よくある質問・トラブルシューティング',
              link: '/guides/faq/',
            },
          ],
        },
        {
          label: 'アドオン解説',
          items: getAddonSidebarItems(),
        },
      ],
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});

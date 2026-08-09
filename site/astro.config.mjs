import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';
import generatePackages from './integrations/generate-packages.mjs';

const base =
  process.env.BASE_PATH ??
  (process.env.GITHUB_ACTIONS ? '/blender-addons' : '/');

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
          items: [
            { label: 'Slide Relax', link: '/addons/slide-relax/' },
            {
              label: 'Smooth Weight',
              link: '/addons/weight-smooth/',
            },
            { label: 'UV Island Mask', link: '/addons/uv-island-mask/' },
          ],
        },
      ],
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});

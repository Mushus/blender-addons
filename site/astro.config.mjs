import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import generatePackages from './integrations/generate-packages.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://mushus.github.io/blender-addons',
  integrations: [
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
            { label: 'UV Island Mask', link: '/addons/uv-island-mask/' },
          ],
        },
      ],
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});

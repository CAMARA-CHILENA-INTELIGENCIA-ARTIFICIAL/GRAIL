import { themes as prismThemes } from "prism-react-renderer";
import type { Config } from "@docusaurus/types";
import type * as Preset from "@docusaurus/preset-classic";

const config: Config = {
  title: "GRAIL",
  tagline: "Un motor de grafo, dos rutas de escritura: base de conocimiento + memoria agéntica",
  favicon: "img/favicon.ico",

  url: "https://grail.nirvana-ai.com",
  baseUrl: "/",

  organizationName: "CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL",
  projectName: "GRAIL",

  onBrokenLinks: "warn",
  onBrokenMarkdownLinks: "warn",

  i18n: {
    defaultLocale: "es",
    locales: ["es", "en"],
    localeConfigs: {
      es: { label: "Español", direction: "ltr", htmlLang: "es-CL" },
      en: { label: "English", direction: "ltr", htmlLang: "en-US" },
    },
  },

  presets: [
    [
      "classic",
      {
        docs: {
          sidebarPath: "./sidebars.ts",
          routeBasePath: "/",
          editUrl:
            "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/tree/master/docs-site/",
        },
        blog: false,
        theme: { customCss: "./src/css/custom.css" },
      } satisfies Preset.Options,
    ],
  ],

  themes: [
    [
      "@easyops-cn/docusaurus-search-local",
      {
        hashed: true,
        language: ["es", "en"],
        indexBlog: false,
        indexPages: true,
        highlightSearchTermsOnTargetPage: true,
        explicitSearchResultPath: true,
        docsRouteBasePath: "/",
        searchBarShortcut: true,
        searchBarShortcutHint: true,
      },
    ],
  ],

  themeConfig: {
    image: "img/social-card.png",
    colorMode: {
      defaultMode: "dark",
      respectPrefersColorScheme: false,
      disableSwitch: false,
    },
    navbar: {
      title: "GRAIL",
      logo: { alt: "GRAIL", src: "img/isotype.png", height: 30 },
      items: [
        { to: "/", label: "Inicio", position: "left", activeBaseRegex: "^/$" },
        { to: "/learn/what-is-grail", label: "Aprende", position: "left", sidebarId: "main" },
        { to: "/start/install", label: "Empieza", position: "left", sidebarId: "main" },
        { to: "/guides", label: "Guías", position: "left", sidebarId: "main" },
        { to: "/reference/cli", label: "Referencia", position: "left", sidebarId: "main" },
        { to: "/cookbook", label: "Recetario", position: "left", sidebarId: "main" },
        { type: "search", position: "right" },
        { type: "localeDropdown", position: "right" },
        {
          href: "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL",
          label: "GitHub",
          position: "right",
        },
      ],
    },
    footer: {
      style: "dark",
      logo: {
        alt: "Cámara Chilena de Inteligencia Artificial",
        src: "img/cchia.png",
        href: "https://cchia.cl",
        width: 200,
      },
      links: [
        {
          title: "Documentación",
          items: [
            { label: "Inicio", to: "/" },
            { label: "Aprende", to: "/learn/what-is-grail" },
            { label: "Empieza", to: "/start/install" },
            { label: "Referencia", to: "/reference/cli" },
            { label: "Recetario", to: "/cookbook" },
          ],
        },
        {
          title: "Proyecto",
          items: [
            { label: "GitHub", href: "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL" },
            { label: "Cámara Chilena de IA", href: "https://cchia.cl" },
            { label: "Nirvai", href: "https://nirvana-ai.com" },
          ],
        },
        {
          title: "Autor",
          items: [
            { label: "Benjamín González Guerrero", href: "mailto:ben@nirvana-ai.com" },
          ],
        },
      ],
      copyright: `Desarrollado bajo la comisión open-source de la Cámara Chilena de Inteligencia Artificial · MIT © ${new Date().getFullYear()}`,
    },
    prism: {
      theme: prismThemes.vsLight,
      darkTheme: prismThemes.vsDark,
      additionalLanguages: ["bash", "python", "yaml", "json"],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;

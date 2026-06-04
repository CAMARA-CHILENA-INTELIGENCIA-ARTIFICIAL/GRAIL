import type { SidebarsConfig } from "@docusaurus/plugin-content-docs";

/**
 * One unified vertical menu shown across every doc page.
 * Each category is collapsible; the active page's category auto-expands.
 */
const sidebars: SidebarsConfig = {
  main: [
    {
      type: "category",
      label: "Aprende",
      collapsible: true,
      collapsed: false,
      link: { type: "doc", id: "learn/what-is-grail" },
      items: [
        "learn/what-is-grail",
        "learn/two-modes",
        "learn/knowledge-graphs-in-5-min",
        "learn/search-modes",
        "learn/cascade",
        "learn/communities-leiden",
        "learn/memory-model",
        "learn/cost-tracking",
      ],
    },
    {
      type: "category",
      label: "Empieza",
      collapsible: true,
      collapsed: false,
      link: { type: "doc", id: "start/install" },
      items: [
        "start/install",
        "start/kb-quickstart",
        "start/memory-quickstart",
        "start/skill-quickstart",
      ],
    },
    {
      type: "category",
      label: "Guías",
      collapsible: true,
      collapsed: true,
      link: { type: "doc", id: "guides/index" },
      items: [
        "guides/web-chat",
        "guides/cli-chat",
        "guides/prompt-tuning",
        "guides/cost-optimization",
        "guides/query-tracing",
        "guides/visualization",
      ],
    },
    {
      type: "category",
      label: "Referencia",
      collapsible: true,
      collapsed: true,
      link: { type: "doc", id: "reference/cli" },
      items: [
        "reference/cli",
        "reference/python-sdk",
      ],
    },
    {
      type: "category",
      label: "Recetario",
      collapsible: true,
      collapsed: true,
      link: { type: "doc", id: "cookbook/index" },
      items: [
        "cookbook/pdf-corpus-qa-bot",
      ],
    },
  ],
};

export default sidebars;

import React from "react";
import Layout from "@theme/Layout";
import Link from "@docusaurus/Link";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";

type ColumnItem = {
  href: string;
  title: string;
  body: string;
};

type Section = {
  eyebrow: string;
  title: string;
  lede: string;
  columns: ColumnItem[];
};

type Copy = {
  // Hero
  tagline: string;
  sub: string;
  meta: string;
  ctaPrimary: string;
  ctaSecondary: string;

  // Modes
  modesTitle: string;
  modesLede: string;
  kbBadge: string;
  kbTitle: string;
  kbBody: string;
  kbCta: string;
  memoryBadge: string;
  memoryTitle: string;
  memoryBody: string;
  memoryCta: string;
  skillBadge: string;
  skillTitle: string;
  skillBody: React.ReactNode;
  skillCta: string;

  // Section blocks
  learn: Section;
  start: Section;
  resources: Section;

  // Footer banner
  bannerEyebrow: string;
  bannerTitle: string;
  bannerLede: string;
  bannerCtaGithub: string;
  bannerCtaDocs: string;

  // Acknowledgements
  ackEyebrow: string;
  ackTitle: string;
  ackGraphragLabel: string;
  ackGraphragBody: React.ReactNode;
  ackCommissionLabel: string;
  ackCommissionBody: React.ReactNode;
  // Slim sponsor strip
  sponsorLabel: string;
  sponsorLink: string;
};

const COPY: Record<string, Copy> = {
  es: {
    tagline: "Un motor de grafo, dos rutas de escritura.",
    sub: "Base de conocimiento consultable sobre tus documentos, y memoria agéntica para Claude Code, Codex y OpenCode.",
    meta: "Open source · Python 3.12 · MIT",
    ctaPrimary: "Empieza en 5 minutos →",
    ctaSecondary: "Aprende qué es GRAIL",

    modesTitle: "Una librería. Dos formas de usarla.",
    modesLede:
      "El mismo motor potencia dos casos de uso distintos sobre los mismos artefactos. Elige por dónde empezar.",
    kbBadge: "Base de conocimiento",
    kbTitle: "Pregúntale a tus documentos",
    kbBody:
      "Apunta GRAIL a una carpeta de PDFs, markdown o código. Indexa una vez, consulta con seis modos de búsqueda — incluyendo un agente que elige la herramienta correcta por cada pregunta.",
    kbCta: "Quickstart KB →",
    memoryBadge: "Memoria agéntica",
    memoryTitle: "Dale memoria a tu agente",
    memoryBody:
      "Conecta GRAIL a Claude Code, Codex u OpenCode. El agente escribe observaciones, entidades y relaciones directamente — sin un paso de extracción por LLM intermedio.",
    memoryCta: "Quickstart memoria →",
    skillBadge: "Skill para agentes",
    skillTitle: "Instala el skill listo para usar",
    skillBody: (
      <>
        Una carpeta portable que funciona en Claude Code, Codex y otros frameworks con formato <code>SKILL.md</code>. Tu agente obtiene memoria persistente en una línea de instalación.
      </>
    ),
    skillCta: "Instalar el skill →",

    learn: {
      eyebrow: "Aprende",
      title: "Conceptos esenciales",
      lede: "Construye intuición antes de los detalles técnicos. Cada página parte con una analogía, sigue con el modelo mental, y termina con los detalles.",
      columns: [
        {
          href: "/learn/what-is-grail",
          title: "¿Qué es GRAIL?",
          body: "La biblioteca, el bibliotecario y el grafo. La idea central en cinco minutos.",
        },
        {
          href: "/learn/two-modes",
          title: "Los dos modos",
          body: "Base de conocimiento vs memoria agéntica, lado a lado. Cuándo elegir cuál.",
        },
        {
          href: "/learn/search-modes",
          title: "Los seis modos de búsqueda",
          body: "Una herramienta por pregunta. Cuándo usar local, cascade, global, document, agent, recall.",
        },
        {
          href: "/learn/cascade",
          title: "Cascade en profundidad",
          body: "Por qué cascade gana en preguntas factuales. Cómo combina grafo con rescate de texto.",
        },
        {
          href: "/learn/memory-model",
          title: "Modelo de memoria",
          body: "Cómo piensa GRAIL la memoria de un agente: observaciones tipadas, carpetas como comunidades, consolidate con propuestas.",
        },
        {
          href: "/learn/cost-tracking",
          title: "Seguimiento honesto de costos",
          body: "Por qué nunca verás un fake $0.00. Cómo presupuestar antes de indexar.",
        },
      ],
    },

    start: {
      eyebrow: "Empieza",
      title: "Cinco minutos para tu primera respuesta",
      lede: "Recetas paso a paso para arrancar. Elige por tu caso de uso.",
      columns: [
        {
          href: "/start/install",
          title: "Instalar GRAIL",
          body: "uv o pip · Python 3.12 · 11 endpoints LLM listos · .env configurado.",
        },
        {
          href: "/start/kb-quickstart",
          title: "Quickstart base de conocimiento",
          body: "De cero a tu primera consulta sobre PDFs propios. Indexar, preguntar, conversar.",
        },
        {
          href: "/start/memory-quickstart",
          title: "Quickstart memoria agéntica",
          body: "Crea un proyecto de memoria, escribe tu primera observación, consulta con recall.",
        },
        {
          href: "/start/skill-quickstart",
          title: "Quickstart skill",
          body: "Instala el skill en Claude Code, Codex u OpenCode. Memoria persistente para tu agente.",
        },
      ],
    },

    resources: {
      eyebrow: "Más recursos",
      title: "Cuando estés más adentro",
      lede: "Guías por tarea, referencia técnica completa, y proyectos end-to-end copy-paste.",
      columns: [
        {
          href: "/guides",
          title: "Guías",
          body: "Cómo optimizar costos, trazar consultas para debug, visualizar el grafo. Recetas concretas para tareas comunes.",
        },
        {
          href: "/reference/cli",
          title: "Referencia CLI",
          body: "Todos los subcomandos de grail con sus flags y ejemplos. La página que abres cuando no recuerdas un parámetro.",
        },
        {
          href: "/reference/python-sdk",
          title: "SDK de Python",
          body: "Las clases GRAIL y MemoryProject. La API que la CLI envuelve. Para embeber GRAIL en tu propia app.",
        },
        {
          href: "/cookbook",
          title: "Recetario",
          body: "Proyectos completos copy-paste. Bot Q&A sobre PDFs, memoria multi-tenant, y más en desarrollo.",
        },
      ],
    },

    bannerEyebrow: "Open source",
    bannerTitle: "Desarrollado en Chile, para el mundo",
    bannerLede:
      "GRAIL se desarrolla bajo la comisión open-source de la Cámara Chilena de Inteligencia Artificial. MIT, sin telemetría, sin captura de proveedor.",
    bannerCtaGithub: "Ver en GitHub →",
    bannerCtaDocs: "Documentación técnica completa →",

    ackEyebrow: "Agradecimientos",
    ackTitle: "Sobre los hombros de quien estamos",
    sponsorLabel: "Patrocinado por",
    sponsorLink: "Visita Nirvai →",
    ackGraphragLabel: "Inspiración técnica",
    ackGraphragBody: (
      <>
        La extracción en una sola pasada por LLM de entidades y relaciones desde chunks de texto en el modo base de conocimiento de GRAIL toma inspiración de{" "}
        <a href="https://github.com/microsoft/graphrag" target="_blank" rel="noopener noreferrer">
          Microsoft GraphRAG
        </a>
        . Todo lo demás — actualizaciones incrementales, recuperación en cascada, el bucle de búsqueda agéntica, el modo de memoria agéntica y su consolidación basada en propuestas, el modo recall, las relaciones tipadas, las consultas de recuperación en entidades, el seguimiento honesto de costos, la procedencia a nivel de archivo y la arquitectura de doble ruta de escritura — es diseño propio de GRAIL.
      </>
    ),
    ackCommissionLabel: "Comisión",
    ackCommissionBody: (
      <>
        GRAIL se desarrolla bajo la comisión open-source de la{" "}
        <a href="https://cchia.cl" target="_blank" rel="noopener noreferrer">
          Cámara Chilena de Inteligencia Artificial
        </a>
        . Autor y creador:{" "}
        <a href="mailto:ben@nirvana-ai.com">Benjamín González Guerrero</a>, fundador de{" "}
        <a href="https://nirvana-ai.com" target="_blank" rel="noopener noreferrer">
          Nirvai
        </a>
        .
      </>
    ),
  },
  en: {
    tagline: "One graph engine, two write paths.",
    sub: "A queryable knowledge base over your documents, and an agentic memory layer for Claude Code, Codex, and OpenCode.",
    meta: "Open source · Python 3.12 · MIT",
    ctaPrimary: "Get started in 5 minutes →",
    ctaSecondary: "Learn what GRAIL is",

    modesTitle: "One library. Two ways to use it.",
    modesLede:
      "The same engine powers two distinct use cases on the same artefacts. Pick where to start.",
    kbBadge: "Knowledge base",
    kbTitle: "Ask your documents",
    kbBody:
      "Point GRAIL at a folder of PDFs, markdown, or code. Index once, query through six search modes — including an agent that picks the right tool for each question.",
    kbCta: "KB quickstart →",
    memoryBadge: "Agentic memory",
    memoryTitle: "Give your agent memory",
    memoryBody:
      "Wire GRAIL into Claude Code, Codex, or OpenCode. The agent writes observations, entities, and relationships directly — no intermediate LLM extraction step.",
    memoryCta: "Memory quickstart →",
    skillBadge: "Agent skill",
    skillTitle: "Install the ready-made skill",
    skillBody: (
      <>
        A portable folder that works in Claude Code, Codex, and other frameworks with the <code>SKILL.md</code> convention. Your agent gets persistent memory in one install command.
      </>
    ),
    skillCta: "Install the skill →",

    learn: {
      eyebrow: "Learn",
      title: "Core concepts",
      lede: "Build intuition before the technical details. Each page starts with an analogy, then the mental model, then the technicals.",
      columns: [
        {
          href: "/learn/what-is-grail",
          title: "What is GRAIL?",
          body: "The library, the librarian, and the graph. The core idea in five minutes.",
        },
        {
          href: "/learn/two-modes",
          title: "The two modes",
          body: "Knowledge base vs agentic memory, side by side. When to pick which.",
        },
        {
          href: "/learn/search-modes",
          title: "The six search modes",
          body: "One tool per question. When to use local, cascade, global, document, agent, recall.",
        },
        {
          href: "/learn/cascade",
          title: "Cascade in depth",
          body: "Why cascade wins on factual questions. How it combines graph with text rescue.",
        },
        {
          href: "/learn/memory-model",
          title: "Memory model",
          body: "How GRAIL thinks about agent memory: typed observations, folders as communities, consolidate proposals.",
        },
        {
          href: "/learn/cost-tracking",
          title: "Honest cost tracking",
          body: "Why you'll never see a fake $0.00. How to budget before you index.",
        },
      ],
    },

    start: {
      eyebrow: "Get started",
      title: "Five minutes to your first answer",
      lede: "Step-by-step recipes to get going. Pick by use case.",
      columns: [
        {
          href: "/start/install",
          title: "Install GRAIL",
          body: "uv or pip · Python 3.12 · 11 LLM endpoints built in · .env ready.",
        },
        {
          href: "/start/kb-quickstart",
          title: "KB quickstart",
          body: "From zero to your first query on your own PDFs. Index, ask, chat.",
        },
        {
          href: "/start/memory-quickstart",
          title: "Memory quickstart",
          body: "Create a memory project, write your first observation, query with recall.",
        },
        {
          href: "/start/skill-quickstart",
          title: "Skill quickstart",
          body: "Install the skill in Claude Code, Codex, or OpenCode. Persistent memory for your agent.",
        },
      ],
    },

    resources: {
      eyebrow: "More resources",
      title: "When you're deeper in",
      lede: "Task-oriented guides, full technical reference, and end-to-end copy-paste projects.",
      columns: [
        {
          href: "/guides",
          title: "Guides",
          body: "How to optimise costs, trace queries for debug, visualise the graph. Concrete recipes for common tasks.",
        },
        {
          href: "/reference/cli",
          title: "CLI reference",
          body: "Every grail subcommand with flags and examples. The page you open when you forget a parameter.",
        },
        {
          href: "/reference/python-sdk",
          title: "Python SDK",
          body: "The GRAIL and MemoryProject classes. The API the CLI wraps. For embedding GRAIL in your own app.",
        },
        {
          href: "/cookbook",
          title: "Cookbook",
          body: "Complete copy-paste projects. PDF Q&A bot, multi-tenant memory, and more in development.",
        },
      ],
    },

    bannerEyebrow: "Open source",
    bannerTitle: "Built in Chile, for the world",
    bannerLede:
      "GRAIL is developed under the open-source commission of the Cámara Chilena de Inteligencia Artificial. MIT-licensed, no telemetry, no vendor lock-in.",
    bannerCtaGithub: "View on GitHub →",
    bannerCtaDocs: "Full technical docs →",

    ackEyebrow: "Acknowledgements",
    ackTitle: "Standing on others' shoulders",
    sponsorLabel: "Sponsored by",
    sponsorLink: "Visit Nirvai →",
    ackGraphragLabel: "Technical inspiration",
    ackGraphragBody: (
      <>
        The single-pass LLM extraction of entities and relationships from text chunks in GRAIL's knowledge-base mode draws inspiration from{" "}
        <a href="https://github.com/microsoft/graphrag" target="_blank" rel="noopener noreferrer">
          Microsoft GraphRAG
        </a>
        . Everything else — incremental updates, cascade retrieval, the agentic search loop, the agentic memory mode and its proposal-based consolidation, recall mode, typed relationships, retrieval queries on entities, honest cost tracking, file-level provenance, and the dual-write-path architecture — is GRAIL's own design.
      </>
    ),
    ackCommissionLabel: "Commission",
    ackCommissionBody: (
      <>
        GRAIL is developed under the open-source commission of the{" "}
        <a href="https://cchia.cl" target="_blank" rel="noopener noreferrer">
          Cámara Chilena de Inteligencia Artificial
        </a>
        . Author and creator:{" "}
        <a href="mailto:ben@nirvana-ai.com">Benjamín González Guerrero</a>, founder of{" "}
        <a href="https://nirvana-ai.com" target="_blank" rel="noopener noreferrer">
          Nirvai
        </a>
        .
      </>
    ),
  },
};

function CardGrid({ section }: { section: Section }): React.ReactElement {
  return (
    <section className="grail-section">
      <div className="grail-section__inner">
        <p className="grail-section__eyebrow">{section.eyebrow}</p>
        <h2 className="grail-section__title">{section.title}</h2>
        <p className="grail-section__lede">{section.lede}</p>

        <div className="grail-section__grid">
          {section.columns.map((item) => (
            <Link key={item.href} className="grail-doc-card" to={item.href}>
              <h3 className="grail-doc-card__title">{item.title}</h3>
              <p className="grail-doc-card__body">{item.body}</p>
              <span className="grail-doc-card__cta">→</span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home(): React.ReactElement {
  const { i18n } = useDocusaurusContext();
  const locale = i18n.currentLocale ?? "es";
  const t = COPY[locale] ?? COPY.es;

  return (
    <Layout title="GRAIL" description={t.sub} wrapperClassName="grail-home">
      <main className="grail-home-main">
        {/* ============= HERO ============= */}
        <div className="grail-hero">
          <div className="grail-hero__inner">
            <img src="/img/logo.png" alt="GRAIL" className="grail-hero__logo" />
            <p className="grail-hero__tagline">{t.tagline}</p>
            <p className="grail-hero__sub">{t.sub}</p>
            <p className="grail-hero__meta">{t.meta}</p>
            <div className="grail-hero__cta">
              <Link className="grail-btn grail-btn--primary" to="/start/install">
                {t.ctaPrimary}
              </Link>
              <Link className="grail-btn grail-btn--ghost" to="/learn/what-is-grail">
                {t.ctaSecondary}
              </Link>
            </div>
          </div>
        </div>

        {/* ============= MODES ============= */}
        <section className="grail-modes">
          <div className="grail-modes__inner">
            <h2 className="grail-modes__title">{t.modesTitle}</h2>
            <p className="grail-modes__lede">{t.modesLede}</p>

            <div className="grail-modes__grid">
              <Link className="grail-mode-card grail-mode-card--kb" to="/start/kb-quickstart">
                <span className="grail-mode-card__badge">{t.kbBadge}</span>
                <h3 className="grail-mode-card__title">{t.kbTitle}</h3>
                <p className="grail-mode-card__body">{t.kbBody}</p>
                <span className="grail-mode-card__cta">{t.kbCta}</span>
              </Link>

              <Link
                className="grail-mode-card grail-mode-card--memory"
                to="/start/memory-quickstart"
              >
                <span className="grail-mode-card__badge">{t.memoryBadge}</span>
                <h3 className="grail-mode-card__title">{t.memoryTitle}</h3>
                <p className="grail-mode-card__body">{t.memoryBody}</p>
                <span className="grail-mode-card__cta">{t.memoryCta}</span>
              </Link>

              <Link className="grail-mode-card grail-mode-card--skill" to="/start/skill-quickstart">
                <span className="grail-mode-card__badge">{t.skillBadge}</span>
                <h3 className="grail-mode-card__title">{t.skillTitle}</h3>
                <p className="grail-mode-card__body">{t.skillBody}</p>
                <span className="grail-mode-card__cta">{t.skillCta}</span>
              </Link>
            </div>
          </div>
        </section>

        {/* ============= LEARN / START / RESOURCES ============= */}
        <CardGrid section={t.learn} />
        <CardGrid section={t.start} />
        <CardGrid section={t.resources} />

        {/* ============= CCHIA BANNER ============= */}
        <section className="grail-banner">
          <div className="grail-banner__inner">
            <a
              href="https://cchia.cl"
              target="_blank"
              rel="noopener noreferrer"
              className="grail-banner__logo-link"
            >
              <img src="/img/cchia.png" alt="Cámara Chilena de IA" className="grail-banner__logo" />
            </a>
            <div className="grail-banner__copy">
              <p className="grail-banner__eyebrow">{t.bannerEyebrow}</p>
              <h2 className="grail-banner__title">{t.bannerTitle}</h2>
              <p className="grail-banner__lede">{t.bannerLede}</p>
              <div className="grail-banner__cta">
                <a
                  className="grail-btn grail-btn--primary"
                  href="https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t.bannerCtaGithub}
                </a>
                <Link className="grail-btn grail-btn--ghost" to="/learn/what-is-grail">
                  {t.bannerCtaDocs}
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* ============= ACKNOWLEDGEMENTS ============= */}
        <section className="grail-ack">
          <div className="grail-ack__inner">
            <p className="grail-ack__eyebrow">{t.ackEyebrow}</p>
            <h2 className="grail-ack__title">{t.ackTitle}</h2>

            <div className="grail-ack__grid">
              <div className="grail-ack__item">
                <h3 className="grail-ack__item-title">{t.ackGraphragLabel}</h3>
                <p className="grail-ack__item-body">{t.ackGraphragBody}</p>
              </div>
              <div className="grail-ack__item">
                <h3 className="grail-ack__item-title">{t.ackCommissionLabel}</h3>
                <p className="grail-ack__item-body">{t.ackCommissionBody}</p>
              </div>
            </div>

            {/* Slim sponsor strip — Nirvai */}
            <a
              href="https://nirvana-ai.com"
              target="_blank"
              rel="noopener noreferrer"
              className="grail-sponsor-strip"
              aria-label="Nirvai"
            >
              <span className="grail-sponsor-strip__label">{t.sponsorLabel}</span>
              <img src="/img/nirvai.webp" alt="Nirvai" className="grail-sponsor-strip__logo" />
              <span className="grail-sponsor-strip__name">Nirvai</span>
              <span className="grail-sponsor-strip__cta">{t.sponsorLink}</span>
            </a>
          </div>
        </section>
      </main>
    </Layout>
  );
}

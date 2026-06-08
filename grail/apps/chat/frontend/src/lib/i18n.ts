import { create } from "zustand";

export type Lang = "en" | "es";

const STORAGE_KEY = "grail.lang";

function detectInitial(): Lang {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "es") return stored;
  const nav = window.navigator.language?.toLowerCase() ?? "";
  return nav.startsWith("es") ? "es" : "en";
}

const STRINGS = {
  en: {
    // ---- Sidebar ----
    "sb.newChat": "New chat",
    "sb.kbLabel": "Knowledge base",
    "sb.collapse": "Collapse sidebar",
    "sb.expand": "Expand sidebar",
    "sb.signOut": "Sign out",
    "sb.delete": "Delete",
    "sb.modeLine": "GRAIL · {mode}",
    "sb.emptyTitle": "No conversations yet.",
    "sb.emptySub": "Start one to build your graph trail.",
    "sb.credit": "Open source by",
    "sb.docs": "Docs",
    "sb.github": "GitHub",
    "sb.groupToday": "Today",
    "sb.groupYesterday": "Yesterday",
    "sb.groupWeek": "Previous 7 days",
    "sb.groupOlder": "Older",
    "sb.untitled": "New chat",
    "sb.viewSwitch": "View",
    "sb.viewChat": "Chat",
    "sb.viewGraph": "Graph",

    // ---- Knowledge graph view ----
    "graph.title": "Knowledge graph",
    "graph.loading": "Loading graph…",
    "graph.refresh": "Refresh",
    "graph.errLoad": "Could not load the graph.",
    "graph.errEmpty": "No entities indexed yet. Run `grail index` first.",
    "graph.truncated": "Showing top {kept} of {total} entities by degree.",
    "graph.loadMore": "Load {n}",
    "graph.loadAll": "Load all",

    // ---- Tool calls ----
    "toolCall.running": "Running…",

    // ---- Welcome ----
    "welcome.lede1": "Ask your",
    "welcome.lede2": "knowledge graph.",
    "welcome.connectedTo": "Connected to",
    "welcome.sub":
      "GRAIL turns your documents into a graph of entities and relationships — then answers from it, with sources you can trace.",
    "welcome.cardAgentTitle": "Agent",
    "welcome.cardAgentDesc":
      "Lets GRAIL decide which searches to run and chain them — best for open-ended questions.",
    "welcome.cardLocalTitle": "Local",
    "welcome.cardLocalDesc":
      "Walks the neighborhood around specific entities. Best for precise, grounded lookups.",
    "welcome.cardGlobalTitle": "Global",
    "welcome.cardGlobalDesc":
      "Map-reduces over community reports. Best for broad themes across the whole corpus.",
    "welcome.recommended": "Recommended",
    "welcome.sample1": "What are the main themes across my documents?",
    "welcome.sample2": "Who is mentioned most in the corpus?",
    "welcome.sample3": "Summarize what changed between versions.",

    // ---- Empty session ----
    "empty.title": "Start the conversation below.",
    "empty.sub": "This session is empty. Ask anything about your indexed corpus.",
    "empty.scopedTo": "Scoped to",
    "empty.mode": "mode · {mode}",

    // ---- Composer ----
    "composer.placeholder": "Ask your knowledge graph…",
    "composer.send": "send",
    "composer.newline": "newline",
    "composer.docScopeTitle": "Scope to a document",
    "composer.helpTitle": "How search works",
    "composer.sendAria": "Send message",
    "composer.scopedTag": "Scoped to",
    "composer.clearScope": "Clear document scope",

    // ---- Mode chips / hints ----
    "mode.agent": "Agent",
    "mode.local": "Local",
    "mode.cascade": "Cascade",
    "mode.global": "Global",
    "mode.rerank": "Rerank",
    "hint.agent": "Agent mode · chains searches automatically",
    "hint.local": "Local search · walks the entity neighborhood",
    "hint.cascade": "Cascade · entity gate + text rescue (BM25/cosine)",
    "hint.global": "Global search · synthesizes community reports",
    "hint.default": "Ask your knowledge graph",

    // ---- Doc picker ----
    "doc.selectTitle": "Select document",
    "doc.clear": "Clear scope",

    // ---- Login ----
    "login.titleSignIn": "Welcome back",
    "login.titleSetup": "Create your account",
    "login.subSignIn": "Sign in to your knowledge graph.",
    "login.subSetup": "Set up credentials to get started.",
    "login.username": "Username",
    "login.password": "Password",
    "login.usernamePlaceholder": "you@cchia.cl",
    "login.passwordPlaceholder": "••••••••••",
    "login.submitSignIn": "Sign in",
    "login.submitSetup": "Create account",
    "login.tagline": "Graph RAG with Advanced Integration and Learning",
    "login.credit": "An open-source project by",

    // ---- Info panel ----
    "info.title": "How search works",
    "info.sub": "GRAIL chooses how to traverse your graph. Four modes, one knowledge base.",
    "info.tagRecommended": "recommended",
    "info.tagEntityFirst": "entity-first",
    "info.tagHybrid": "hybrid",
    "info.tagThemeFirst": "theme-first",
    "info.tagOptional": "optional",
    "info.agentDesc":
      "An LLM loop that decides which searches to run and chains them. Best when the question spans entities and themes, or you're not sure where to look.",
    "info.localDesc":
      "Anchors on the entities in your question and walks their neighborhood — relationships, attributes, and the chunks that mention them. Precise and grounded.",
    "info.cascadeDesc":
      "Entity-gated retrieval with BM25/cosine text rescue. Catches answers that live in the text even when no single entity captures them. Best for specific facts.",
    "info.globalDesc":
      "Map-reduces across community reports built during indexing. Best for broad, corpus-wide questions where no single entity holds the answer.",
    "info.rerankDesc":
      "When a reranker is configured, candidate passages are re-scored for relevance before synthesis — sharpening citations on dense corpora.",
    "info.close": "Close",

    // ---- Message bubble ----
    "msg.docSearchTag": "Document search",
    "msg.sources": "Sources",
    "msg.download": "Download",
    "msg.askAgent": "Ask agent about this document",
    "msg.llmCall": "{n} LLM call",
    "msg.llmCalls": "{n} LLM calls",
    "msg.source": "{n} source",
    "msg.sources_n": "{n} sources",
    "msg.sourceFallback": "source",
  },

  es: {
    // ---- Sidebar ----
    "sb.newChat": "Nuevo chat",
    "sb.kbLabel": "Base de conocimiento",
    "sb.collapse": "Contraer panel",
    "sb.expand": "Expandir panel",
    "sb.signOut": "Cerrar sesión",
    "sb.delete": "Eliminar",
    "sb.modeLine": "GRAIL · {mode}",
    "sb.emptyTitle": "Aún no hay conversaciones.",
    "sb.emptySub": "Inicia una para empezar a explorar el grafo.",
    "sb.credit": "Código abierto por",
    "sb.docs": "Docs",
    "sb.github": "GitHub",
    "sb.groupToday": "Hoy",
    "sb.groupYesterday": "Ayer",
    "sb.groupWeek": "Últimos 7 días",
    "sb.groupOlder": "Más antiguos",
    "sb.untitled": "Nuevo chat",
    "sb.viewSwitch": "Vista",
    "sb.viewChat": "Chat",
    "sb.viewGraph": "Grafo",

    // ---- Vista de grafo de conocimiento ----
    "graph.title": "Grafo de conocimiento",
    "graph.loading": "Cargando el grafo…",
    "graph.refresh": "Refrescar",
    "graph.errLoad": "No se pudo cargar el grafo.",
    "graph.errEmpty": "Aún no hay entidades. Ejecuta `grail index` primero.",
    "graph.truncated": "Mostrando las {kept} entidades más conectadas de {total}.",
    "graph.loadMore": "Cargar {n}",
    "graph.loadAll": "Cargar todo",

    // ---- Llamadas a herramientas ----
    "toolCall.running": "Ejecutando…",

    // ---- Welcome ----
    "welcome.lede1": "Pregúntale a tu",
    "welcome.lede2": "grafo de conocimiento.",
    "welcome.connectedTo": "Conectado a",
    "welcome.sub":
      "GRAIL convierte tus documentos en un grafo de entidades y relaciones — y luego responde a partir de él, con fuentes que puedes rastrear.",
    "welcome.cardAgentTitle": "Agente",
    "welcome.cardAgentDesc":
      "Deja que GRAIL decida qué búsquedas ejecutar y las encadene — ideal para preguntas abiertas.",
    "welcome.cardLocalTitle": "Local",
    "welcome.cardLocalDesc":
      "Recorre el vecindario alrededor de entidades específicas. Mejor para búsquedas precisas y fundamentadas.",
    "welcome.cardGlobalTitle": "Global",
    "welcome.cardGlobalDesc":
      "Aplica map-reduce sobre los reportes de comunidades. Ideal para temas amplios en todo el corpus.",
    "welcome.recommended": "Recomendado",
    "welcome.sample1": "¿Cuáles son los temas principales en mis documentos?",
    "welcome.sample2": "¿Quién es mencionado más en el corpus?",
    "welcome.sample3": "Resume qué cambió entre versiones.",

    // ---- Empty session ----
    "empty.title": "Comienza la conversación abajo.",
    "empty.sub": "Esta sesión está vacía. Pregunta lo que quieras sobre tu corpus indexado.",
    "empty.scopedTo": "Limitado a",
    "empty.mode": "modo · {mode}",

    // ---- Composer ----
    "composer.placeholder": "Pregúntale a tu grafo de conocimiento…",
    "composer.send": "enviar",
    "composer.newline": "salto",
    "composer.docScopeTitle": "Limitar a un documento",
    "composer.helpTitle": "Cómo funciona la búsqueda",
    "composer.sendAria": "Enviar mensaje",
    "composer.scopedTag": "Limitado a",
    "composer.clearScope": "Quitar documento",

    // ---- Mode chips / hints ----
    "mode.agent": "Agente",
    "mode.local": "Local",
    "mode.cascade": "Cascada",
    "mode.global": "Global",
    "mode.rerank": "Rerank",
    "hint.agent": "Modo agente · encadena búsquedas automáticamente",
    "hint.local": "Búsqueda local · recorre el vecindario de entidades",
    "hint.cascade": "Cascada · entidad + rescate por texto (BM25/coseno)",
    "hint.global": "Búsqueda global · sintetiza reportes de comunidades",
    "hint.default": "Pregúntale a tu grafo de conocimiento",

    // ---- Doc picker ----
    "doc.selectTitle": "Seleccionar documento",
    "doc.clear": "Quitar selección",

    // ---- Login ----
    "login.titleSignIn": "Bienvenido de vuelta",
    "login.titleSetup": "Crea tu cuenta",
    "login.subSignIn": "Inicia sesión en tu grafo de conocimiento.",
    "login.subSetup": "Configura tus credenciales para empezar.",
    "login.username": "Usuario",
    "login.password": "Contraseña",
    "login.usernamePlaceholder": "tu@cchia.cl",
    "login.passwordPlaceholder": "••••••••••",
    "login.submitSignIn": "Iniciar sesión",
    "login.submitSetup": "Crear cuenta",
    "login.tagline": "Graph RAG con Integración y Aprendizaje Avanzados",
    "login.credit": "Un proyecto de código abierto por",

    // ---- Info panel ----
    "info.title": "Cómo funciona la búsqueda",
    "info.sub": "GRAIL elige cómo recorrer tu grafo. Cuatro modos, una sola base de conocimiento.",
    "info.tagRecommended": "recomendado",
    "info.tagEntityFirst": "primero entidades",
    "info.tagHybrid": "híbrido",
    "info.tagThemeFirst": "primero temas",
    "info.tagOptional": "opcional",
    "info.agentDesc":
      "Un bucle de LLM que decide qué búsquedas ejecutar y las encadena. Ideal cuando la pregunta cruza entidades y temas, o no estás seguro dónde buscar.",
    "info.localDesc":
      "Se ancla en las entidades de tu pregunta y recorre su vecindario — relaciones, atributos y los fragmentos que las mencionan. Precisa y fundamentada.",
    "info.cascadeDesc":
      "Recuperación con compuerta de entidad + rescate por texto (BM25/coseno). Captura respuestas que viven en el texto incluso cuando ninguna entidad las captura. Ideal para datos específicos.",
    "info.globalDesc":
      "Aplica map-reduce sobre los reportes de comunidades construidos durante la indexación. Ideal para preguntas amplias donde ninguna entidad concentra la respuesta.",
    "info.rerankDesc":
      "Cuando hay un reranker configurado, los pasajes candidatos se re-puntúan por relevancia antes de la síntesis — afilando citas en corpus densos.",
    "info.close": "Cerrar",

    // ---- Message bubble ----
    "msg.docSearchTag": "Búsqueda en documento",
    "msg.sources": "Fuentes",
    "msg.download": "Descargar",
    "msg.askAgent": "Preguntar al agente sobre este documento",
    "msg.llmCall": "{n} llamada LLM",
    "msg.llmCalls": "{n} llamadas LLM",
    "msg.source": "{n} fuente",
    "msg.sources_n": "{n} fuentes",
    "msg.sourceFallback": "fuente",
  },
} as const;

export type StringKey = keyof typeof STRINGS.en;

interface I18nState {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

export const useI18nStore = create<I18nState>((set) => ({
  lang: detectInitial(),
  setLang: (lang) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, lang);
      window.document.documentElement.lang = lang;
    }
    set({ lang });
  },
}));

if (typeof window !== "undefined") {
  // sync <html lang> on first paint
  window.document.documentElement.lang = useI18nStore.getState().lang;
}

function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : `{${key}}`,
  );
}

export function useT() {
  const lang = useI18nStore((s) => s.lang);
  return (key: StringKey, vars?: Record<string, string | number>): string => {
    const table = STRINGS[lang] as Record<string, string>;
    const template = table[key] ?? (STRINGS.en as Record<string, string>)[key] ?? key;
    return format(template, vars);
  };
}

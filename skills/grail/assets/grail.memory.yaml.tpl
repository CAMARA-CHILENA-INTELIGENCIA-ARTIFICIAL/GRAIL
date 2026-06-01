# GRAIL project config (memory mode).

project_name: {name}
root_dir: {root}
mode: memory

# LLM optional — recall mode + tool writes work without it.
llm:
  endpoint: openai
  model: gpt-4o-mini

embeddings:
  endpoint: deepinfra
  model: intfloat/multilingual-e5-large

indexing:
  parse_frontmatter: true
  relationship_types:
    - RELATED
    - MENTIONS
    - WORKS_AT
    - OWNS
    - LOCATED_IN
    - CAUSES
    - PART_OF
    - CONTRADICTS
    - SUPERSEDES
    - OBSERVED_AT
    - ASSOCIATED_WITH
    - DEPENDS_ON
  entity_types:
    - person
    - organization
    - location
    - event
    - concept

memory:
  min_entities_for_consolidate: 30
  auto_commit: false

storage:
  backend: local
  root: {root}

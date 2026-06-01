# GRAIL project config (knowledge_base mode).
# Drop source files into ./input/ and run `grail index <project>`.

project_name: {name}
root_dir: {root}
mode: knowledge_base

llm:
  endpoint: openai
  model: gpt-4o-mini

embeddings:
  endpoint: deepinfra
  model: intfloat/multilingual-e5-large

indexing:
  entity_types:
    - person
    - organization
    - location
    - event
    - concept

storage:
  backend: local
  root: {root}

# Indexing pipeline

> **Scope.** Turning source files into a queryable knowledge graph. Configures: ``configs/indexing.yaml``. Code: ``grail/indexing/``.

## Stages

```
FileLoader → EntityRelationshipExtractor → CommunityExtractor → CommunityReportGenerator
   ↓                  ↓                            ↓                       ↓
partial_text_units  final_entities             final_nodes          final_community_reports
final_docs          final_relationships        final_communities    
mapping.json        final_text_units           
                    entity_relationship_graph.graphml
```

Each stage reads its predecessors' parquet artefacts off storage, so you can
re-run individual stages by hand (``await CommunityExtractor.extract_communities()``
expects ``entity_relationship_graph.graphml`` to exist).

## FileLoader

Walks ``{root}/input/``, reads text-like files, and produces:

* ``final_docs.parquet`` — one row per source file.
* ``partial_text_units.parquet`` — one row per chunk.
* ``mapping.json`` — keyed by doc id → original path + metadata.

**Mixed-document chunking.** All input files are concatenated with a configurable
``document_boundary`` separator. The result is chunked once, and the contributing
document_ids are recorded on each chunk. This is the legacy "mixed content"
strategy: it improves locality without losing provenance, because each chunk
remembers exactly which source files it overlaps.

Knobs in ``configs/indexing.yaml``:

```yaml
chunk_size: 2000
chunk_overlap: 50
encoding_name: cl100k_base
document_boundary: "\n\n---DOCUMENT_BOUNDARY---\n\n"
```

v0.1 supports ``text``, ``code``, and ``data`` file types per
:func:`grail.utils.detect_data_type`. PDF / Office / image extraction is a
later-phase hook — slot a pre-processing step into ``FileLoader._read_one``
that returns plain text per file.

## EntityRelationshipExtractor

For each chunk, asks the LLM (via the ``entity_relation`` prompt) for entities
and relationships in the GraphRAG tuple format:

```
("entity"<|>NAME<|>TYPE<|>DESC)## ("relationship"<|>SRC<|>TGT<|>DESC<|>STRENGTH)<|COMPLETE|>
```

The parser is contract-bound to ``DEFAULT_DELIMITERS`` in
``grail/prompts/builtin/entity_relation.py``. Custom prompt packs that change the
delimiters must either keep the same exports or override the extractor's
``delimiters`` kwarg directly.

Outputs:

* ``final_entities.parquet`` — id, name, type, description, description_embedding, text_unit_ids, document_ids, degree.
* ``final_relationships.parquet`` — id, source, target, description, weight (averaged), rank.
* ``final_text_units.parquet`` — original text units + ``entity_ids`` and ``relationship_ids`` they mention.
* ``entity_relationship_graph.graphml`` — NetworkX graph with embeddings serialised.

Entities are deduplicated by uppercase title; multi-description entities are
re-summarized by :class:`SummarizeExtractor` before embedding. Relationships are
deduplicated by ``(source, target)`` pair, descriptions summarized, weights averaged.

## CommunityExtractor

Runs hierarchical Leiden via ``graspologic`` (configured in
``configs/community.yaml``). Embedding-based merging combines communities below
``min_community_size`` via DBSCAN over their entity-embedding centroids
(``embedding_merge_eps=0.5`` by default).

Outputs:

* ``final_nodes.parquet`` — per-level node assignments.
* ``final_communities.parquet`` — per-level community membership.

Knobs:

```yaml
max_cluster_size: 50
use_lcc: false                    # restrict to largest connected component before clustering
seed: null                        # set for reproducibility
min_community_size: 10
embedding_merge_eps: 0.5
```

## CommunityReportGenerator

For each top-level community, asks the LLM (via ``community_report``) for a JSON
report:

```json
{
  "title": "string",
  "summary": "string",
  "rating": 0-10,
  "rating_explanation": "string",
  "findings": [{"summary": "string", "explanation": "string"}, ...]
}
```

Three-pass JSON repair:

1. Direct ``json.loads``.
2. Strip code fences / outer junk and parse again.
3. Ask the LLM (``json_correction`` prompt) to fix the broken JSON.

Output: ``final_community_reports.parquet``.

Knobs:

```yaml
community_report_model: null      # falls back to llm.default_model
json_corrector_model: null
max_report_length: 4000           # max_output_tokens for reports
include_covariates: false         # covariates (claims) are off in v0.1
```

## IncrementalCommunityExtractor

Applied by ``GRAIL.append`` / ``GRAIL.edit`` / ``GRAIL.delete``. Computes a
change ratio (affected entities ÷ total). When the ratio is below
``incremental_change_threshold`` (default 0.3), new nodes inherit their
highest-weight neighbour's community via label propagation — cheap and roughly
preserves structure. Above the threshold the extractor delegates to the base
:class:`CommunityExtractor` to re-cluster the whole graph. (A future phase will
narrow this to the affected subgraph; for v0.1 the full re-cluster is the safe
default.)

## Tuning per-model

The default model set is biased toward Qwen / DeepInfra. If you point GRAIL at
GPT-4o-mini or Claude, you'll usually want:

* ``max_gleanings: 0`` (already the default) — gleaning passes are an upstream
  graphrag setting that re-asks for missed entities. Costly, often not worth it.
* Tighter ``chunk_size`` (1200-1500) for smaller-context models.
* ``response_format: {"type": "json_object"}`` is already passed for
  community-report and JSON-correction calls.

If a model returns no parseable entities, the most common cause is that it
rewrote the delimiter format. Add a JSON-mode entity extraction prompt to your
custom pack rather than re-engineering the parser.

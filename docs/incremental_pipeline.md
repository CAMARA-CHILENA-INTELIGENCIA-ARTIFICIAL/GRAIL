"""
Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""

# Incremental Pipeline

GRAIL supports three incremental operations — **append**, **edit**, and
**delete** — that update the knowledge graph without rebuilding it from
scratch. Each operation propagates through three layers, each feeding the
next.

---

## Full Indexing Pipeline (reference)

Before understanding the incremental path, here is the full pipeline that
`grail.index()` runs:

```mermaid
flowchart TD
    SRC["Source Files"]

    subgraph L1["Layer 1 — FileLoader"]
        L1A["Discover files"] --> L1B["Read content"]
        L1B --> L1C["Chunk with TokenTextSplitter"]
        L1C --> L1D["Track document boundaries"]
    end

    subgraph L2["Layer 2 — EntityRelationshipExtractor"]
        L2A["LLM extraction per chunk"] --> L2B["Parse tuple format"]
        L2B --> L2C["Dedup by entity name / rel pair"]
        L2C --> L2D["Summarize multi-descriptions"]
        L2D --> L2E["Embed entity descriptions"]
        L2E --> L2F["Build NetworkX graph"]
    end

    subgraph L3["Layer 3 — CommunityExtractor"]
        L3A["Hierarchical Leiden clustering"] --> L3B["DBSCAN small-cluster merge"]
        L3B --> L3C["Tag nodes with community IDs"]
    end

    subgraph L4["Layer 4 — CommunityReportGenerator"]
        L4A["Build CSV context per community"] --> L4B["LLM generates JSON report"]
        L4B --> L4C["3-pass JSON repair"]
    end

    SRC --> L1
    L1 --> L2
    L2 --> L3
    L3 --> L4

    L1 -. "final_docs.parquet
    partial_text_units.parquet
    mapping.json" .-> OUT1[("Storage")]
    L2 -. "final_entities.parquet
    final_relationships.parquet
    final_text_units.parquet
    entity_relationship_graph.graphml" .-> OUT1
    L3 -. "final_nodes.parquet
    final_communities.parquet" .-> OUT1
    L4 -. "final_community_reports.parquet" .-> OUT1
```

---

## The Incremental Architecture

### Central Mechanism: Text-Unit Reference Tracking

Every entity and relationship stores a `text_unit_ids` list — the IDs of text
chunks that mention it. This provenance chain is the backbone of incremental
updates.

```mermaid
erDiagram
    SOURCE_FILE ||--o{ DOCUMENT : "produces"
    DOCUMENT ||--o{ TEXT_UNIT : "chunked into (1:N)"
    TEXT_UNIT }o--o{ ENTITY : "mentions (M:N via text_unit_ids)"
    TEXT_UNIT }o--o{ RELATIONSHIP : "mentions (M:N via text_unit_ids)"
    ENTITY }o--o{ COMMUNITY : "belongs to"
    RELATIONSHIP ||--|| ENTITY : "source"
    RELATIONSHIP ||--|| ENTITY : "target"

    SOURCE_FILE {
        string path
        string content
    }
    DOCUMENT {
        string id PK
        string title
        string raw_content
        list text_unit_ids
    }
    TEXT_UNIT {
        string id PK
        string text
        int n_tokens
        list document_ids
    }
    ENTITY {
        string id PK
        string name
        string type
        string description
        list text_unit_ids
        list description_embedding
    }
    RELATIONSHIP {
        string id PK
        string source
        string target
        float weight
        list text_unit_ids
    }
    COMMUNITY {
        string id PK
        int level
        list entity_ids
    }
```

When a file is edited or deleted, the text units change. We trace the impact
through `text_unit_ids` to find which entities and relationships are affected,
update their references, and prune those that become orphaned (zero remaining
references).

---

### Data Flow per Operation

#### Append (add new files)

```mermaid
flowchart LR
    NEW["New files"] --> COPY["Copy into input/"]

    subgraph Layer1["Layer 1: FileLoader.append_files()"]
        CHUNK["Chunk ONLY new files"] --> MERGE_TU["Concatenate with existing parquets"]
    end

    subgraph Layer2["Layer 2: EntityRelationshipExtractor.append_extract()"]
        direction TB
        LLM["LLM extraction on new TUs only"]
        LLM --> DUP{"Entity name exists?"}
        DUP -- Yes --> RESUMM["Combine descriptions
        re-summarize via LLM
        merge text_unit_ids
        re-embed"]
        DUP -- No --> NEWENT["Create new entity
        embed description"]
        RESUMM --> GRAPH["Rebuild graph"]
        NEWENT --> GRAPH
    end

    subgraph Layer3["Layer 3: IncrementalCommunityExtractor.update()"]
        RATIO{"change_ratio
        < threshold?"}
        RATIO -- "Yes (< 0.3)" --> LP["Label propagation
        O(new_nodes)"]
        RATIO -- "No (>= 0.3)" --> LEIDEN["Full Leiden
        re-clustering"]
    end

    REPORTS["Layer 4: Generate community reports"]

    COPY --> Layer1
    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> REPORTS
```

#### Edit (replace file content)

```mermaid
flowchart LR
    REPL["Replacement files"] --> COPYEDIT["Replace in input/"]

    subgraph Layer1["Layer 1: FileLoader.batch_edit_documents()"]
        direction TB
        FIND["Find ALL text units
        referencing edited docs
        (incl. mixed chunks)"]
        FIND --> REMOVE["Remove affected TUs"]
        REMOVE --> RECHUNK["Re-chunk affected
        document groups
        with new content"]
    end

    subgraph Layer2["Layer 2: EntityRelationshipExtractor.edit_extract()"]
        direction TB
        STRIP["Strip old TU refs
        from all entities/rels"]
        STRIP --> LLME["LLM extraction on
        replacement TUs"]
        LLME --> MERGEE["Merge new extractions
        with existing"]
        MERGEE --> PRUNE["Prune orphaned entities
        (text_unit_ids == [])
        Prune orphaned rels
        (dangling endpoints)"]
    end

    subgraph Layer3["Layer 3: IncrementalCommunityExtractor.incremental_edit()"]
        direction TB
        DELN["Remove deleted
        entity nodes"] --> RATIOE{"change_ratio
        < threshold?"}
        RATIOE -- Yes --> LPE["Label propagation"]
        RATIOE -- No --> LEIDE["Full Leiden"]
    end

    REPORTSE["Layer 4: Regenerate reports"]

    COPYEDIT --> Layer1
    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> REPORTSE
```

#### Delete (remove files)

```mermaid
flowchart LR
    DEL["File names to delete"]

    subgraph Layer1["Layer 1: FileLoader.batch_delete_documents()"]
        direction TB
        LOOKUP["Look up doc IDs
        by filename"]
        LOOKUP --> COLLECT["Collect text_unit_ids
        belonging to those docs"]
        COLLECT --> REMDOCS["Remove docs + TUs
        from parquets"]
        REMDOCS --> DELSRC["Delete source files
        from input/"]
    end

    subgraph Layer2["Layer 2: EntityRelationshipExtractor.delete_extract()"]
        direction TB
        STRIPD["Strip deleted TU IDs
        from all entities/rels"]
        STRIPD --> PRUNED["Prune entities with
        zero text_unit refs"]
        PRUNED --> PRUNER["Prune rels with
        dangling endpoints"]
        NOLLM["No LLM calls needed"]
        style NOLLM fill:#e8f5e9,stroke:#4caf50
    end

    subgraph Layer3["Layer 3: IncrementalCommunityExtractor.incremental_delete()"]
        direction TB
        REMNODES["Remove deleted nodes
        from graph"]
        REMNODES --> PRUNECOMM["Prune empty
        communities"]
    end

    REPORTSD["Layer 4: Regenerate reports"]

    DEL --> Layer1
    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> REPORTSD
```

---

### Side-by-Side: What Each Operation Touches

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '14px'}}}%%
block-beta
    columns 4
    space header1["Append"] header2["Edit"] header3["Delete"]

    lbl1["FileLoader"]:1
    a1["Chunk new files
    Concat parquets"]:1
    e1["Find affected TUs
    Re-chunk groups"]:1
    d1["Remove docs + TUs
    Delete source files"]:1

    lbl2["Entity/Rel
    Extractor"]:1
    a2["LLM on new TUs
    Merge by name"]:1
    e2["Strip refs + LLM
    Merge + Prune"]:1
    d2["Strip refs
    Prune orphans
    (no LLM)"]:1

    lbl3["Community
    Extractor"]:1
    a3["Label prop
    or Leiden"]:1
    e3["Delete nodes
    Label prop / Leiden"]:1
    d3["Delete nodes
    Prune empty"]:1

    lbl4["Report
    Generator"]:1
    a4["Generate all"]:1
    e4["Regenerate"]:1
    d4["Regenerate"]:1

    style a2 fill:#fff3e0,stroke:#ff9800
    style e2 fill:#fff3e0,stroke:#ff9800
    style d2 fill:#e8f5e9,stroke:#4caf50
```

---

## Key Design Decisions

### Selective LLM Calls

Only new or changed text units go through LLM extraction. For a 1000-document
corpus where you append 5 files, only those 5 files' chunks hit the LLM —
the existing 995 files' entities and relationships are preserved as-is.

For delete operations, **no LLM calls are needed at all** in Layer 2. The
operation is pure data manipulation: strip references, prune orphans.

```mermaid
pie title LLM calls: Append 5 files to 1000-doc corpus
    "New file extraction (5 docs)" : 5
    "Skipped — existing (995 docs)" : 995
```

### Selective Re-Embedding

Entity description embeddings are expensive. The incremental path only
re-embeds entities whose descriptions actually changed:

| Operation | Re-embed? | Why |
|-----------|-----------|-----|
| **Append** — new entity | Yes | No prior embedding exists |
| **Append** — merged entity | Yes | Description was re-summarized |
| **Append** — untouched entity | No | Description unchanged |
| **Edit** — updated entity | Yes | Description was re-summarized |
| **Edit** — orphaned entity | No | Entity is deleted entirely |
| **Delete** — any entity | No | Either unchanged or deleted |

### Mixed-Document Chunk Handling

Text units can span multiple documents when chunks straddle a
`---DOCUMENT_BOUNDARY---`. This means editing one document can affect chunks
that also contain content from adjacent documents.

```mermaid
flowchart TD
    subgraph Before["Before Edit"]
        D1["Doc A content"] --- B1["---BOUNDARY---"] --- D2["Doc B content"]
        D1 & B1 & D2 --> TU1["Text Unit 1
        (Doc A + Doc B)
        document_ids: [A, B]"]
    end

    subgraph Edit["Edit Doc A"]
        D1E["Doc A NEW content"] --- B1E["---BOUNDARY---"] --- D2E["Doc B content (unchanged)"]
    end

    subgraph After["After Edit"]
        D1E & B1E & D2E --> TU2["Text Unit 1' (new)
        Re-chunked with new A + old B
        document_ids: [A, B]"]
    end

    Before --> |"batch_edit_documents()"| Edit --> After
```

`batch_edit_documents` handles this by:
1. Finding all text units that reference *any* edited doc (via `document_ids`)
2. Grouping them by their document combination
3. Re-assembling the combined content (using new content for edited docs,
   existing content for untouched docs in the same group)
4. Re-chunking the combined content

### Orphan Cleanup

The pruning logic ensures the graph stays clean:

```mermaid
flowchart TD
    subgraph check["For each entity / relationship"]
        TU{"text_unit_ids
        empty?"}
        TU -- Yes --> ORPHAN["ORPHAN — prune
        from graph"]
        TU -- No --> KEEP["KEEP — still
        referenced"]
    end

    subgraph relcheck["For each relationship"]
        EP{"Source or target
        entity pruned?"}
        EP -- Yes --> RORPHAN["ORPHAN — prune
        relationship"]
        EP -- No --> RKEEP["KEEP — both
        endpoints exist"]
    end

    style ORPHAN fill:#ffebee,stroke:#f44336
    style RORPHAN fill:#ffebee,stroke:#f44336
    style KEEP fill:#e8f5e9,stroke:#4caf50
    style RKEEP fill:#e8f5e9,stroke:#4caf50
```

### Community Update Strategy

The `IncrementalCommunityExtractor` uses a change-ratio scheduler:

```mermaid
flowchart TD
    CALC["change_ratio = (new + updated + deleted) / total entities"]

    CALC --> CHECK{"ratio < threshold
    (default 0.3)"}

    CHECK -- "Yes — minor change" --> LP["Label Propagation"]
    CHECK -- "No — major change" --> LEIDEN["Full Leiden Re-clustering"]

    subgraph lpdetail["Label Propagation (cheap)"]
        LP --> LP1["For each new node:"]
        LP1 --> LP2["Find highest-weight neighbor"]
        LP2 --> LP3["Inherit neighbor's community ID"]
        LP3 --> LP4["Isolated nodes get fresh IDs"]
    end

    subgraph leidendetail["Full Leiden (accurate)"]
        LEIDEN --> LE1["Run hierarchical_leiden() on full graph"]
        LE1 --> LE2["DBSCAN merge small communities"]
        LE2 --> LE3["Re-assign all community IDs"]
    end

    style LP fill:#e8f5e9,stroke:#4caf50
    style LEIDEN fill:#fff3e0,stroke:#ff9800
```

The threshold is configurable via `community.incremental_change_threshold` in
the YAML config.

---

## Class Diagram

```mermaid
classDiagram
    class GRAIL {
        +Config config
        +StorageBackend storage
        +LLMClient llm
        +EmbeddingClient embeddings
        +index() dict
        +append(new_files) dict
        +edit(replacements) dict
        +delete(file_names) dict
        +search(query, mode) SearchResult
        -_make_loader() FileLoader
        -_make_extractor() EntityRelationshipExtractor
        -_make_community_extractor() CommunityExtractor
        -_make_incremental_community() IncrementalCommunityExtractor
    }

    class FileLoader {
        +build_text_units(keys) tuple
        +append_files(new_keys) tuple
        +batch_edit_documents(edits) tuple
        +batch_delete_documents(doc_ids) tuple
        +get_doc_ids_by_path(filenames) list
        +write_artifacts()
        +load_artifacts() tuple
    }

    class EntityRelationshipExtractor {
        +process_text_units() tuple
        +append_extract(df, ids) tuple
        +edit_extract(df, ids) tuple
        +delete_extract(df, ids) tuple
        -_extract_raw(df) tuple
        -_merge_with_existing() tuple
        -_strip_text_unit_refs()
        -_prune_orphan_entities()
        -_prune_orphan_relationships()
    }

    class IncrementalCommunityExtractor {
        +float change_threshold
        +update(graph, new, updated) tuple
        +incremental_edit(graph, new, updated, deleted) tuple
        +incremental_delete(graph, deleted) tuple
        -_label_propagate(graph, new_names) tuple
    }

    class CommunityExtractor {
        +extract_communities(graph) tuple
    }

    class CommunityReportGenerator {
        +generate_reports() DataFrame
    }

    GRAIL --> FileLoader : creates
    GRAIL --> EntityRelationshipExtractor : creates
    GRAIL --> IncrementalCommunityExtractor : creates
    GRAIL --> CommunityReportGenerator : creates
    IncrementalCommunityExtractor --> CommunityExtractor : delegates to
```

---

## Parquet Artifact Reference

| File | Producer | Key Columns |
|------|----------|-------------|
| `final_docs.parquet` | FileLoader | `id, text_unit_ids, raw_content, title, path` |
| `partial_text_units.parquet` | FileLoader | `id, text, n_tokens, document_id, document_ids` |
| `final_text_units.parquet` | EntityRelationshipExtractor | + `entity_ids, relationship_ids` |
| `final_entities.parquet` | EntityRelationshipExtractor | `id, name, type, description, description_embedding, text_unit_ids, document_ids, degree` |
| `final_relationships.parquet` | EntityRelationshipExtractor | `id, source, target, description, weight, text_unit_ids, document_ids, rank` |
| `entity_relationship_graph.graphml` | EntityRelationshipExtractor | NetworkX graph |
| `final_nodes.parquet` | CommunityExtractor | `level, community, title, id, type, description, degree` |
| `final_communities.parquet` | CommunityExtractor | `id, level, community, entity_ids, size` |
| `final_community_reports.parquet` | CommunityReportGenerator | `id, community, title, summary, full_content, rank` |
| `mapping.json` | FileLoader | `doc_id -> {original_path, title, extension, data_type, size_chars}` |

---

## Configuration

```yaml
community:
  incremental_change_threshold: 0.3   # ratio above which full re-clustering triggers
  max_cluster_size: 50                 # Leiden max cluster size
  min_community_size: 10               # DBSCAN merge threshold for small communities
  embedding_merge_eps: 0.5             # DBSCAN epsilon for centroid-based merge
```

---

## API

```python
grail = GRAIL.from_config("grail.yaml")

# Full index (first time)
result = await grail.index()

# Append new files (incremental)
result = await grail.append(["new_doc.txt", "another.pdf"])

# Edit existing files (incremental)
result = await grail.edit({"old_doc.txt": "/path/to/new_version.txt"})

# Delete files (incremental)
result = await grail.delete(["unwanted.txt"])
```

Each operation returns a dict with operation-specific metrics:

```python
{
    "ok": True,
    "operation": "append",
    "duration_s": 12.3,
    "new_files": 2,
    "new_text_units": 8,
    "new_entities": 15,
    "updated_entities": 3,
    "total_entities": 218,
    "total_relationships": 456,
    "communities": 12,
    "reports": 12,
    "llm_summary": {...},
}
```

---

## Sequence Diagram: Append Operation

```mermaid
sequenceDiagram
    actor User
    participant GRAIL as GRAIL (core.py)
    participant FL as FileLoader
    participant ERE as EntityRelationshipExtractor
    participant ICE as IncrementalCommunityExtractor
    participant CRG as CommunityReportGenerator
    participant LLM as LLM API
    participant EMB as Embedding API
    participant VS as VectorStore

    User->>GRAIL: append(["new_file.txt"])
    GRAIL->>FL: copy_in() + append_files(new_keys)
    FL->>FL: load existing parquets
    FL->>FL: build_text_units(keys=new_keys)
    FL-->>GRAIL: (docs_df, text_units_df, mapping, new_tu_ids)
    GRAIL->>FL: write_artifacts()

    GRAIL->>ERE: append_extract(text_units_df, new_tu_ids)
    ERE->>LLM: extract entities from new TUs only
    LLM-->>ERE: raw extraction responses
    ERE->>ERE: parse + dedup
    ERE->>ERE: load existing entities/rels parquets
    ERE->>ERE: merge by entity name
    ERE->>LLM: re-summarize changed descriptions
    LLM-->>ERE: summaries
    ERE->>EMB: re-embed changed entities
    EMB-->>ERE: embeddings
    ERE-->>GRAIL: (entities_df, rels_df, graph, new_names, updated_names)

    GRAIL->>VS: update_vector_store(entities_df)

    GRAIL->>ICE: update(graph, new_names, updated_names)
    ICE->>ICE: compute change_ratio
    alt ratio < 0.3
        ICE->>ICE: label propagation
    else ratio >= 0.3
        ICE->>ICE: full Leiden re-clustering
    end
    ICE-->>GRAIL: (graph, communities, nodes_df, comm_df)

    GRAIL->>CRG: generate_reports()
    CRG->>LLM: summarize each community
    LLM-->>CRG: JSON reports
    CRG-->>GRAIL: reports_df

    GRAIL-->>User: {"ok": true, "new_entities": 15, ...}
```

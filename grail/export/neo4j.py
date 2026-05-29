"""
Export a GRAIL knowledge graph to Neo4j.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Reads parquet artifacts (entities, relationships, text units, documents,
communities, community reports) and pushes them into a Neo4j database via
Cypher MERGE statements.  The schema follows the Microsoft GraphRAG / GRAIL
convention with double-underscore marker labels:

    __Document__, __Chunk__, __Entity__, __Community__, Finding

Relationships: PART_OF, HAS_ENTITY, RELATED, IN_COMMUNITY, HAS_FINDING

Requires ``neo4j`` Python driver (``pip install neo4j``).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import pandas as pd

log = logging.getLogger(__name__)


class Reporter(Protocol):
    def info(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...


class _NullReporter:
    def info(self, msg: str) -> None: pass
    def success(self, msg: str) -> None: pass
    def warning(self, msg: str) -> None: pass


CONSTRAINTS = [
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:__Chunk__) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:__Document__) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:__Community__) REQUIRE c.community IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:__Entity__) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:__Entity__) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT related_id IF NOT EXISTS FOR ()-[rel:RELATED]->() REQUIRE rel.id IS UNIQUE",
]

IMPORT_DOCUMENTS = """
MERGE (d:__Document__ {id: value.id})
SET d += value {.title}
"""

IMPORT_TEXT_UNITS = """
MERGE (c:__Chunk__ {id: value.id})
SET c += value {.text, .n_tokens}
WITH c, value
UNWIND value.document_ids AS document
MATCH (d:__Document__ {id: document})
MERGE (c)-[:PART_OF]->(d)
"""

IMPORT_ENTITIES = """
MERGE (e:__Entity__ {id: value.id})
SET e += value {.human_readable_id, .description, name: replace(value.name, '"', '')}
WITH e, value
CALL apoc.create.addLabels(e, CASE WHEN coalesce(value.type, '') = '' THEN [] ELSE [apoc.text.upperCamelCase(replace(value.type, '"', ''))] END) YIELD node
UNWIND value.text_unit_ids AS text_unit
MATCH (c:__Chunk__ {id: text_unit})
MERGE (c)-[:HAS_ENTITY]->(e)
"""

IMPORT_ENTITIES_NO_APOC = """
MERGE (e:__Entity__ {id: value.id})
SET e += value {.human_readable_id, .description, name: replace(value.name, '"', '')}
WITH e, value
UNWIND value.text_unit_ids AS text_unit
MATCH (c:__Chunk__ {id: text_unit})
MERGE (c)-[:HAS_ENTITY]->(e)
"""

IMPORT_RELATIONSHIPS = """
MATCH (source:__Entity__ {name: replace(value.source, '"', '')})
MATCH (target:__Entity__ {name: replace(value.target, '"', '')})
MERGE (source)-[rel:RELATED {id: value.id}]->(target)
SET rel += value {.rank, .weight, .human_readable_id, .description, .text_unit_ids}
RETURN count(*) as createdRels
"""

IMPORT_COMMUNITIES = """
MERGE (c:__Community__ {community: value.id})
SET c += value {.level, .title}
WITH *
UNWIND value.relationship_ids AS rel_id
MATCH (start:__Entity__)-[:RELATED {id: rel_id}]->(end:__Entity__)
MERGE (start)-[:IN_COMMUNITY]->(c)
MERGE (end)-[:IN_COMMUNITY]->(c)
RETURN count(DISTINCT c) AS createdCommunities
"""

IMPORT_COMMUNITY_REPORTS = """
MERGE (c:__Community__ {community: value.community})
SET c += value {.level, .title, .rank, .rank_explanation, .full_content, .summary}
WITH c, value
UNWIND range(0, size(value.findings) - 1) AS finding_idx
WITH c, value, finding_idx, value.findings[finding_idx] AS finding
MERGE (c)-[:HAS_FINDING]->(f:Finding {id: value.community + '-' + toString(finding_idx)})
SET f += finding
"""


def _safe_list_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Ensure a column that should be a list is actually a list (parquet can store as numpy arrays)."""
    if col not in df.columns:
        return df
    df = df.copy()
    df[col] = df[col].apply(lambda v: list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else ([] if v is None else [v]))
    return df


def _safe_findings(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the findings column is a list of dicts."""
    if "findings" not in df.columns:
        df = df.copy()
        df["findings"] = [[] for _ in range(len(df))]
        return df
    df = df.copy()
    def _parse(v: Any) -> list:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    df["findings"] = df["findings"].apply(_parse)
    return df


@dataclass
class Neo4jExportResult:
    documents: int = 0
    text_units: int = 0
    entities: int = 0
    relationships: int = 0
    communities: int = 0
    community_reports: int = 0
    elapsed: float = 0.0


def export_to_neo4j(
    *,
    uri: str,
    username: str,
    password: str,
    database: str = "neo4j",
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    text_units: pd.DataFrame,
    documents: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    batch_size: int = 500,
    clear_graph: bool = False,
    use_apoc: bool = True,
    reporter: Optional[Reporter] = None,
) -> Neo4jExportResult:
    """Push GRAIL artifacts into a Neo4j database.

    Args:
        uri: Neo4j Bolt URI (e.g. ``neo4j+s://xxx.databases.neo4j.io``).
        username: Neo4j username (typically ``"neo4j"``).
        password: Neo4j password.
        database: Target database name.
        entities / relationships / ...: DataFrames from GRAIL parquet output.
        batch_size: Rows per Cypher transaction.
        clear_graph: If True, wipe the database before importing.
        use_apoc: If True, use APOC procedures for dynamic labels on entities.
        reporter: Optional progress reporter (CLI styled output).

    Returns:
        :class:`Neo4jExportResult` with row counts and timing.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise ImportError(
            "The 'neo4j' package is required for Neo4j export.\n"
            "Install it with:  pip install neo4j"
        )

    rep = reporter or _NullReporter()
    result = Neo4jExportResult()
    t0 = time.time()

    rep.info(f"Connecting to {uri}…")
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        driver.verify_connectivity()
        rep.success("Connected to Neo4j")
    except Exception as exc:
        raise ConnectionError(
            f"Could not connect to Neo4j at {uri}.\n"
            f"Error: {exc}\n\n"
            "Check your NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD."
        ) from exc

    db_kwargs: dict[str, Any] = {}
    if database:
        db_kwargs["database_"] = database

    def _batch_import(statement: str, df: pd.DataFrame, label: str) -> int:
        total = len(df)
        if total == 0:
            rep.info(f"  {label}: 0 rows, skipping")
            return 0
        for start in range(0, total, batch_size):
            batch = df.iloc[start:min(start + batch_size, total)]
            driver.execute_query(
                "UNWIND $rows AS value " + statement,
                rows=batch.to_dict("records"),
                **db_kwargs,
            )
        rep.success(f"  {label}: {total} rows")
        return total

    try:
        if clear_graph:
            rep.info("Clearing existing graph data…")
            driver.execute_query("MATCH (n) DETACH DELETE n", **db_kwargs)
            rep.success("Graph cleared")

        rep.info("Creating constraints…")
        for stmt in CONSTRAINTS:
            try:
                driver.execute_query(stmt, **db_kwargs)
            except Exception as exc:
                log.debug("Constraint may already exist: %s — %s", stmt[:60], exc)
        rep.success("Constraints ready")

        rep.info("Importing graph data…")

        # Documents
        if not documents.empty:
            result.documents = _batch_import(
                IMPORT_DOCUMENTS,
                documents[["id", "title"]],
                "Documents",
            )

        # Text units
        if not text_units.empty:
            tu = _safe_list_col(text_units, "document_ids")
            cols = ["id", "text", "n_tokens", "document_ids"]
            cols = [c for c in cols if c in tu.columns]
            result.text_units = _batch_import(IMPORT_TEXT_UNITS, tu[cols], "Text units")

        # Entities
        if not entities.empty:
            ent = _safe_list_col(entities, "text_unit_ids")
            cols = ["name", "type", "description", "human_readable_id", "id", "text_unit_ids"]
            cols = [c for c in cols if c in ent.columns]
            stmt = IMPORT_ENTITIES if use_apoc else IMPORT_ENTITIES_NO_APOC
            result.entities = _batch_import(stmt, ent[cols], "Entities")

        # Relationships
        if not relationships.empty:
            rel = _safe_list_col(relationships, "text_unit_ids")
            cols = ["source", "target", "id", "rank", "weight", "human_readable_id", "description", "text_unit_ids"]
            cols = [c for c in cols if c in rel.columns]
            result.relationships = _batch_import(IMPORT_RELATIONSHIPS, rel[cols], "Relationships")

        # Communities
        if not communities.empty:
            comm = _safe_list_col(communities, "relationship_ids")
            comm = _safe_list_col(comm, "text_unit_ids")
            cols = ["id", "level", "title", "text_unit_ids", "relationship_ids"]
            cols = [c for c in cols if c in comm.columns]
            result.communities = _batch_import(IMPORT_COMMUNITIES, comm[cols], "Communities")

        # Community reports
        if not community_reports.empty:
            cr = _safe_findings(community_reports)
            cols = ["id", "community", "level", "title", "summary", "findings", "rank", "rank_explanation", "full_content"]
            cols = [c for c in cols if c in cr.columns]
            result.community_reports = _batch_import(IMPORT_COMMUNITY_REPORTS, cr[cols], "Community reports")

    finally:
        driver.close()

    result.elapsed = time.time() - t0
    rep.success(f"Export complete in {result.elapsed:.1f}s")
    return result

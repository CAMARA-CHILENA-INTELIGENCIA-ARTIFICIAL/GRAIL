# Consolidate proposal review workflow

`consolidate.py` runs four analyses against the graph and writes a yaml
file with one proposal per signal. The agent then reviews and applies
each proposal individually. **Nothing mutates** until `apply_proposal`
is called.

## The four proposal kinds

| Kind | Signal | Apply effect |
|---|---|---|
| `discover_community` | Densely-connected entities that span ≥2 declared folders. | Adds a `kind="discovered"` row to `final_communities`; appends the new community id to each member's `community_ids`. |
| `merge_aliases` | Two entity names with Jaro-Winkler ≥ 0.92 (or embedding cosine ≥ 0.93). | Rewrites all relationships to point at the canonical name; drops the alias row from `final_entities`. |
| `move_entity` | Entity has >50% of edges going to a community it's not declared in. | Appends that community to the entity's `community_ids`. |
| `split_folder` | Folder with ≥ N entities bimodally splits into two cohesive sub-clusters. | **Does not move files.** Generates `output/proposals/<id>_apply.sh` with the move commands; marks proposal `accepted-pending-manual`. |

## Lifecycle

```
consolidate  →  yaml(pending)  →  list_proposals  →  apply_proposal --accept|--reject
```

`status` transitions:

```
pending  →  accepted          (auto-applies for discover_community / merge_aliases / move_entity)
pending  →  accepted-pending-manual   (split_folder — agent must run the .sh script)
pending  →  rejected
```

When **all** proposals in a set reach a non-pending status, the file is
moved to `output/proposals/archive/`. `latest.yaml` is removed at the
same time, so the next `consolidate` run starts clean.

## Inspecting a proposal

```bash
python scripts/memory/list_proposals.py --project work-memory
python scripts/memory/list_proposals.py --project work-memory --status pending
```

Each proposal carries `rationale` (human-readable), `confidence` (0–1),
`payload` (kind-specific fields), and `evidence` (the numbers behind the
confidence). Sample:

```yaml
- id: 01HFZP3J0001
  kind: discover_community
  status: pending
  confidence: 0.82
  rationale: |
    ALICE, BOB, CARLOS co-occur with internal density 0.89 across folders
    [work/clients/acme, work/projects/grail].
  payload:
    members: [ALICE, BOB, CARLOS]
    suggested_id: discovered/alice-bob-carlos
  evidence:
    internal_density: 0.89
    member_count: 3
    shared_folders: [work/clients/acme, work/projects/grail]
```

## Acting on proposals

```bash
# Accept by full id or unambiguous prefix
python scripts/memory/apply_proposal.py --project work-memory \
  --id 01HFZP3J --accept

# Reject with a reason for the audit log
python scripts/memory/apply_proposal.py --project work-memory \
  --id 01HFZP3K --reject --reason "noise — these aren't really linked"
```

## When the agent should accept

- **Discover community** with confidence ≥ 0.7 and ≥3 members → safe.
- **Merge aliases** with confidence ≥ 0.92 and shared text_units → safe.
- **Move entity** with confidence ≥ 0.7 → safe (pure metadata change).
- **Split folder** — always require human-style review. The shell
  script is just generated; nothing destructive happens until the
  script runs.

## When the agent should reject

- Anything where the rationale doesn't make sense to the user.
- Proposals whose `payload.members` cross conceptual boundaries the
  agent recognises but the analysis doesn't (e.g. a coincidental
  co-occurrence).
- Proposals on a corpus the user is about to delete or reorganise.

Always pass `--reason` on rejection — it goes into the proposal's
`resolved_reason` field and the `_history.jsonl` audit log.

## Re-running consolidate

`consolidate` is **idempotent on a settled graph** — running it twice
in a row on unchanged data produces zero new pending proposals.

You can re-run it any time. Already-resolved proposals from a previous
run live under `output/proposals/archive/` and never come back unless
the underlying signal still holds.

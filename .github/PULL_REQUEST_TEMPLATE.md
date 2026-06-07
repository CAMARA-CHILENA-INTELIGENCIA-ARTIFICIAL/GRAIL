<!--
Thanks for opening a PR! Before submitting, please confirm there is an
approved issue this PR closes — see CONTRIBUTING.md for the flow.
-->

## Linked issue

<!-- A PR without an approved issue gets `status:needs-approval` and won't be reviewed. -->

Closes #

**Issue status:** <!-- check that the linked issue carries `status:approved` -->

## Category

<!-- Pick one. Must match the linked issue's category label. -->

- [ ] `category:inference-providers`
- [ ] `category:multimodal`
- [ ] `category:agentic-logic`
- [ ] `category:search-methods`
- [ ] `category:indexing-methods`
- [ ] `category:vector-stores`
- [ ] `category:cloud-integrations`
- [ ] `category:library-addition`
- [ ] `category:visual-apps`

## Summary

<!-- 1–3 sentences. What changes, and why. -->

## Implementation notes

<!-- Anything non-obvious for the reviewer: design trade-offs, gotchas, files of interest. -->

---

## Category-specific checklist

<details>
<summary><strong>Inference provider</strong></summary>

- [ ] Endpoint added to `configs/endpoints.yaml`
- [ ] Pricing added to the price book (or `extra_pricing` documented)
- [ ] At least one smoke test indexing + querying a small corpus
- [ ] README endpoint list updated (ES + EN)

</details>

<details>
<summary><strong>Multimodal capability</strong></summary>

- [ ] Design doc landed in `dev_prompts/`
- [ ] Schema changes documented in PR description
- [ ] Unit tests for the new modality path
- [ ] End-to-end example under `examples/`
- [ ] Docs page under `/guides/` or `/learn/` (ES + EN)

</details>

<details>
<summary><strong>Agentic logic</strong></summary>

- [ ] Tool implementation + tests
- [ ] System prompt diff included in PR
- [ ] Benchmark delta measured against `benchmarks/simple_benchmark/`
- [ ] `/learn/search-modes` page reflects the change (ES + EN)

</details>

<details>
<summary><strong>Search method</strong></summary>

- [ ] Implementation under `grail/query/`
- [ ] Wired into `GRAIL.search()` (and `MemoryProject.recall()` if applicable)
- [ ] CLI `--mode <name>` works end-to-end
- [ ] Unit tests
- [ ] Benchmark run included
- [ ] Docs page at `/learn/<method-name>` (ES + EN)
- [ ] README "Search modes" table updated (ES + EN)

</details>

<details>
<summary><strong>Indexing method</strong></summary>

- [ ] Implementation under `grail/indexing/`
- [ ] Schema migration tested with existing fixtures
- [ ] Incremental ops (`append`/`edit`/`delete`) tested if affected
- [ ] Benchmark + cost deltas in PR description
- [ ] Migration notes if schema-breaking

</details>

<details>
<summary><strong>Vector store</strong></summary>

- [ ] `BaseVectorStore` subclass with all 7 methods
- [ ] Optional install extra in `pyproject.toml`
- [ ] Unit tests against a real instance
- [ ] CLI `--vectorstore <name>` works
- [ ] README + docs site backends tables updated (ES + EN)

</details>

<details>
<summary><strong>Cloud integration</strong></summary>

- [ ] Implementation in `grail/storage/` or `grail/cloud/`
- [ ] Optional install extra in `pyproject.toml`
- [ ] Integration test (real or mocked)
- [ ] Env var docs in `.env.example`
- [ ] Docs page under `/guides/` (ES + EN)

</details>

<details>
<summary><strong>Library addition</strong></summary>

- [ ] Added to `pyproject.toml` with version pin
- [ ] License compatibility verified (MIT / Apache / BSD)
- [ ] Lockfile (`uv.lock`) regenerated and committed
- [ ] CI passes with and without the optional extra
- [ ] Install docs updated if user-visible (ES + EN)

</details>

<details>
<summary><strong>Visual app</strong></summary>

- [ ] Frontend `dist/` rebuilt (web)
- [ ] Strings localised (ES + EN) where applicable
- [ ] Screenshots updated in docs guide
- [ ] Manual test on at least one desktop browser, mobile (web), and one terminal (TUI)

</details>

---

## Tests

- [ ] `uv run pytest` passes
- [ ] New tests cover the changed code path
- [ ] Existing tests still pass

## Docs

- [ ] User-visible changes documented in `docs-site/` (ES + EN)
- [ ] Internal architecture notes added to `docs/` if non-obvious
- [ ] README updated if behaviour or surface area changed

## Backwards compatibility

- [ ] No schema-breaking changes, or migration notes included
- [ ] No config-breaking changes, or migration notes included
- [ ] No public-API-breaking changes, or deprecation notes included

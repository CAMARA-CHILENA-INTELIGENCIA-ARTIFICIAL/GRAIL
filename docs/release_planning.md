# Release planning — milestones, tags, and the human flow

> **Audience:** GRAIL maintainers and contributors.
>
> **What this doc covers:** the *planning* side of releases — how features get bundled into a future version, how the flow goes from idea → issue → PR → merge → tag → release, and how to coordinate work across contributors.
>
> **What this doc does NOT cover:** the PyPI publish mechanics (tokens, build, upload). For that, see [`docs/releasing.md`](releasing.md). The two docs are siblings; this one is what you read *before* you reach for `releasing.md`.

---

## 1. The four primitives

GitHub gives you four distinct things that are often confused. Understanding the difference is most of the work:

| Primitive | What it is | Lifespan | Example |
|---|---|---|---|
| **Milestone** | A planning container — "issues/PRs going into release X.Y.Z" | Created → items added → closed when shipped | `v0.1.4` (open, gathering issues) |
| **Git tag** | An immutable marker on a specific commit — "this commit *is* the release" | Forever — points to one commit | `v0.1.3` (a sha on `master`) |
| **GitHub Release** | The publication object built on top of a tag — notes, attached assets, changelog | Forever, attached to a tag | The release page for `v0.1.3` with auto-generated notes |
| **Label** | A categorisation chip on an issue/PR | Permanent label set; applied to any number of items | `category:visual-apps`, `status:approved` |

**The flow uses all four:** a feature lives in a milestone while planned, a label tags its category, a PR closes the milestone item, a git tag freezes the shipping commit, and a GitHub Release publishes the human-readable notes.

---

## 2. Versioning policy

GRAIL follows **semver** (`MAJOR.MINOR.PATCH`) with conventions tuned for the pre-1.0 phase:

| Bump | When | Examples |
|---|---|---|
| **PATCH** (`v0.1.3 → v0.1.4`) | Bug fixes; additive non-breaking small features; doc-only releases; new optional extras | Web graph viz behind an existing CLI command; new optional vector store extra |
| **MINOR** (`v0.1.x → v0.2.0`) | New search modes; new indexing methods; schema additions; new categories of functionality; non-breaking config additions | New `temporal` search mode; new agent tool; multimodal capability landing |
| **MAJOR** (`v0.x.y → v1.0.0`) | First stable release (commitment to backward-compatible 0→1 transition); after 1.0, only for breaking changes | Schema-breaking changes; renaming public API; removing a search mode |

**Pre-1.0 rule:** breaking changes are allowed in any minor bump (`v0.1.x → v0.2.0`), but they should be called out in the release notes. The implicit contract changes once you ship `v1.0.0`.

**Tag format:** always `vMAJOR.MINOR.PATCH` (with the `v` prefix). The PyPI publish workflow (`.github/workflows/publish.yml`) triggers on `v*` tag pushes.

---

## 3. The release flow, generic

This is the canonical step-by-step. The next section walks through a real example.

### 3.1 Open the milestone (planning phase)

Pick the next version number. Create a milestone with that title and a 1–3 sentence description of the theme:

```bash
gh api -X POST repos/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/milestones \
  -f title='vX.Y.Z' \
  -f description='Short theme. What kind of changes go in here.'
```

Or in the UI: **Issues → Milestones → New milestone**.

### 3.2 Add work to the milestone

Two ways work lands in a milestone:

- **Issue-first** (the default flow per [CONTRIBUTING.md](../CONTRIBUTING.md)): contributor opens issue → maintainer applies `status:approved` → maintainer also sets the milestone via the right sidebar of the issue page → contributor opens PR → PR auto-inherits the milestone if linked via `Closes #N`
- **PR-first** (for small fixes you're doing yourself): branch + commit + open PR → set milestone on the PR

When a PR with a milestone gets merged, the milestone progress bar moves forward.

### 3.3 Cut the release (shipping phase)

When the milestone hits 100% (or you decide what's in is enough):

```bash
# 1. Pull the latest master
git checkout master && git pull

# 2. Bump pyproject.toml to the new version
# (edit grail/_version.py or pyproject.toml depending on layout)

# 3. Commit the version bump
git add pyproject.toml grail/_version.py
git commit -m "release: bump to X.Y.Z"

# 4. Tag the commit (annotated tag with a message)
git tag -a vX.Y.Z -m "vX.Y.Z — short theme"

# 5. Push the tag (this triggers the PyPI publish workflow)
git push origin master
git push origin vX.Y.Z

# 6. Close the milestone
gh api -X PATCH repos/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/milestones/<num> -f state=closed

# 7. Create the GitHub Release with auto-generated notes
gh release create vX.Y.Z \
  --title "vX.Y.Z — short theme" \
  --generate-notes
```

`--generate-notes` builds the release notes from the titles of all PRs merged since the previous tag. You can then edit the release notes to add a human-curated summary at the top.

### 3.4 Post-release housekeeping

- Confirm the PyPI publish workflow succeeded (Actions tab)
- Confirm the new version is installable: `uv pip install -U graphgrail==X.Y.Z`
- Announce on Discussions / Slack / wherever you announce
- Update any "current version" references in docs if you maintain them by hand

For the full PyPI mechanics see [`docs/releasing.md`](releasing.md).

---

## 4. Worked example: shipping v0.1.4 (web graph viz)

This is the concrete walkthrough for a real upcoming release.

**Goal:** ship the interactive web-based graph visualisation that was developed under `grail/viz/web/`.

### Step 1 — Create the milestone

```bash
gh api -X POST repos/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/milestones \
  -f title='v0.1.4' \
  -f description='Web-based interactive graph visualisation served from grail viz, plus surfacing it through the agent skill. Patch release: additive, no schema or config changes.'
```

You'll get back a JSON with `"number": N` — that's the milestone number you'll use to assign issues.

### Step 2 — Open the issue (using the visual-app template)

In the GitHub UI:

1. Navigate to `https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/issues/new/choose`
2. Click **"09 · Visual app"**
3. Fill in:
   - **Which app?** New app (graph viz web)
   - **Type of change?** New feature
   - **Describe the change:** "Adds an interactive HTML-based graph viz served from a small local server when running `grail viz --serve`. Supersedes the static HTML output for interactive exploration. The skill scripts gain a `grail-viz` entry point."
   - **Acceptance criteria:** ticked appropriately
4. Submit

The template auto-applies `category:visual-apps` + `status:proposed`.

### Step 3 — Approve the issue and assign it to the milestone

In the right sidebar of the issue page:

- Click `Labels` → add `status:approved`
- Click `Milestone` → pick `v0.1.4`

Or via CLI:

```bash
gh issue edit <issue-number> \
  --add-label "status:approved" \
  --remove-label "status:proposed" \
  --milestone "v0.1.4"
```

### Step 4 — Open the PR

```bash
# From the working tree where the viz code already lives:
git checkout -b feat/web-viz
git add grail/viz/ examples/quickstart/graph.html
git commit -m "feat: web-based interactive graph viz"
git push -u origin feat/web-viz

gh pr create \
  --title "feat: web-based interactive graph viz" \
  --body "Closes #<issue-number>"
```

The PR template will load with the category-aware checklist. Tick `category:visual-apps`, then walk through that section's checklist.

### Step 5 — Assign the PR to the milestone

```bash
gh pr edit <pr-number> --milestone "v0.1.4"
```

Now the milestone progress bar shows the PR as in-flight.

### Step 6 — Self-review and squash-merge

Approve your own PR (branch protection requires 1 approval; only you have write access). Click **Squash and merge**. The branch auto-deletes, `master` advances by one commit. Milestone hits 100%.

### Step 7 — Bump the version, tag, release

```bash
git checkout master && git pull

# Edit grail/_version.py (or wherever __version__ lives) to "0.1.4"
sed -i '' 's/0.1.3/0.1.4/' grail/_version.py    # macOS
# sed -i 's/0.1.3/0.1.4/' grail/_version.py     # Linux

git add grail/_version.py
git commit -m "release: bump to 0.1.4"
git push

git tag -a v0.1.4 -m "v0.1.4 — web graph viz"
git push origin v0.1.4
```

The `v0.1.4` tag push triggers `.github/workflows/publish.yml` → PyPI release goes out automatically.

### Step 8 — Close the milestone and publish the release notes

```bash
gh api -X PATCH repos/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/milestones/<num> -f state=closed

gh release create v0.1.4 \
  --title "v0.1.4 — Web graph visualisation" \
  --generate-notes
```

The release page now exists at `https://github.com/.../releases/tag/v0.1.4` with auto-generated notes from the PR titles. Edit if you want a human summary at the top.

---

## 5. Hotfix flow

When a released version has a critical bug and you need to ship a fix *now*:

```bash
# 1. Branch off the existing tag (not master, in case master has unrelated WIP)
git checkout -b hotfix/v0.1.4-search-crash v0.1.4

# 2. Apply the fix, commit
git add ...
git commit -m "fix: avoid divide-by-zero when corpus has 1 entity"

# 3. Open PR, get it merged (squash) to master via normal flow

# 4. From the new master, bump patch and tag
git checkout master && git pull
# bump grail/_version.py: 0.1.4 → 0.1.5
git commit -am "release: bump to 0.1.5"
git tag -a v0.1.5 -m "v0.1.5 — hotfix: search crash on tiny corpora"
git push origin master v0.1.5

# 5. Release notes
gh release create v0.1.5 --title "v0.1.5 — Hotfix" --generate-notes
```

You don't need to create a milestone for hotfixes — they're single-PR events.

---

## 6. Pre-release tags (alpha / beta / rc)

For risky changes you want to test in the wild before declaring them stable, use pre-release tags:

```bash
git tag -a v0.2.0-alpha.1 -m "v0.2.0-alpha.1 — first cut of multimodal"
git push origin v0.2.0-alpha.1

gh release create v0.2.0-alpha.1 \
  --title "v0.2.0-alpha.1" \
  --generate-notes \
  --prerelease
```

The `--prerelease` flag marks the release as pre-release on GitHub (users see a "Pre-release" badge). PyPI handles these naturally as PEP 440 pre-release versions (`0.2.0a1`).

---

## 7. Coordinating multiple contributors

Once GRAIL has more than one active contributor, the milestone becomes the coordination point:

- **Maintainer triages incoming issues** weekly, assigns each approved issue to a milestone
- **Contributors browse milestones** to find work matching their interests
- **The "good first issue" label** can be combined with a milestone to surface entry-level tasks: `category:* + status:approved + good first issue + milestone:v0.X.Y`
- **The progress bar at `https://github.com/.../milestones`** tells everyone where the next release stands

For a kanban view across milestones, add a single **GitHub Project (v2)** board. The default "Backlog / In Progress / Done" columns pull state from the existing `status:*` labels. Overkill for a solo maintainer; useful at ≥5 active contributors.

---

## 8. CLI cheatsheet

```bash
# Milestones
gh api repos/OWNER/REPO/milestones                          # list open milestones
gh api -X POST repos/OWNER/REPO/milestones \
  -f title='v0.1.4' -f description='...'                    # create
gh api -X PATCH repos/OWNER/REPO/milestones/N \
  -f state=closed                                           # close
gh issue list --milestone "v0.1.4"                          # see what's in it
gh issue edit N --milestone "v0.1.4"                        # add to milestone
gh pr edit N --milestone "v0.1.4"                           # add a PR to a milestone

# Tags
git tag -a vX.Y.Z -m "vX.Y.Z — short theme"                 # create annotated tag
git push origin vX.Y.Z                                      # push (triggers PyPI publish)
git tag --list                                              # list local tags
git ls-remote --tags origin                                 # list remote tags

# Releases
gh release create vX.Y.Z --title "..." --generate-notes     # create with auto-notes
gh release create vX.Y.Z --generate-notes --prerelease      # mark as pre-release
gh release view vX.Y.Z                                      # view the release page
gh release list                                             # all releases
gh release delete vX.Y.Z                                    # remove (rarely needed)
```

---

## 9. Common gotchas

| Problem | Cause | Fix |
|---|---|---|
| Tag pushed but PyPI didn't publish | Tag pushed but `publish.yml` failed | Check Actions tab; if a transient failure, re-run; if the version was already on PyPI, bump and retag |
| `--generate-notes` produces empty notes | Previous release tag has weird metadata | Check `gh release list`; manually pass `--notes-start-tag vPREV` to scope the changelog |
| Milestone progress stuck at 50% | Issue closed but PR didn't auto-close it | Edit the PR description to add `Closes #N` and retry, or manually close the issue |
| Tag exists on remote but not locally | Someone else tagged | `git fetch --tags` |
| Need to undo a tag | Tag was pushed by accident | `git tag -d vX.Y.Z && git push --delete origin vX.Y.Z`. **Don't do this for tags that triggered a PyPI publish** — release a `vX.Y.Z+1` instead |
| Branch protection prevents merging a release-bump commit | The version-bump commit needs a PR | Either open a tiny PR for the bump (overkill), or use the admin bypass for this specific commit |

---

## 10. Why this matters even for a solo maintainer

GRAIL is currently one person plus AI sessions. The milestone flow seems like ceremony. But:

1. **External contributors discover scope through milestones** — they can self-select which release they want to help with
2. **The release-notes-from-PRs pattern frees you** from maintaining a separate CHANGELOG.md
3. **PyPI publish triggers off tag pushes** — the tag is the single point of release; nothing else to coordinate
4. **Future co-maintainers inherit a clear contract** — they don't have to ask "how do releases work here?" because this doc answers it

The ceremony is the *coordination protocol*. Even solo, following it builds the muscle for when others join.

---

## See also

- [`docs/releasing.md`](releasing.md) — PyPI publish mechanics, token setup, build/upload runbook
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the issue + PR flow that feeds into milestones
- [`.github/workflows/publish.yml`](../.github/workflows/publish.yml) — the CI that triggers on `v*` tag pushes

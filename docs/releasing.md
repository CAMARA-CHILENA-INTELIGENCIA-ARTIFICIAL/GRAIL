# Releasing a new GRAIL version

This is the runbook for cutting a `graphgrail` release on PyPI.

There are two release paths:

- **Preferred — push a tag, CI publishes.** Bump `pyproject.toml`,
  commit, tag `vX.Y.Z`, push. `.github/workflows/publish.yml` runs the
  test suite, verifies the tag matches the pyproject version, builds,
  publishes to PyPI, and opens a GitHub Release. See §0 below.
- **Manual fallback — `uv publish` from your laptop.** When the CI
  workflow is broken / unavailable, or you want a controlled TestPyPI
  dry run. See §3 onwards.

> **Distribution name vs import name**
> The PyPI package is `graphgrail` (the `grail` name on PyPI was taken
> by an unrelated test framework). The Python import path stays
> `import grail` and the CLI binary stays `grail`. Users do:
> `pip install graphgrail[faiss]` then `from grail import GRAIL`.

---

## 0. CI-driven release (preferred)

Once the GitHub secrets and PyPI tokens from §1 are in place, every
release boils down to:

```bash
# 1. Bump pyproject.toml ``version = "X.Y.Z"``.
$EDITOR pyproject.toml

# 2. Commit + tag + push.
git add pyproject.toml
git commit -m "Release vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

The workflow does:

1. Runs `pytest tests/unit/`. If anything is red, the publish is
   skipped — no broken release ships.
2. Verifies the pushed tag matches `pyproject.toml` (catches "forgot
   to bump version" mistakes).
3. `uv build` produces the wheel + sdist.
4. `uv publish` uploads to PyPI using the `PYPI_TOKEN` repo secret.
5. Creates a GitHub Release with auto-generated notes and the install
   command.

### TestPyPI dry runs via the same workflow

In the GitHub UI: **Actions → Publish to PyPI → Run workflow**. Pick
`testpypi` (the default). The workflow runs the same steps but
publishes to TestPyPI using the `TESTPYPI_TOKEN` secret. Verify in a
clean venv:

```bash
uv pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               graphgrail
```

If you want to manually re-publish a build to real PyPI from the
dispatcher (e.g. after a TestPyPI dry run on the same SHA), pick
`pypi` as the target.

### Required GitHub repository secrets

Settings → Secrets and variables → Actions → "New repository secret":

| Secret name | Value | Used for |
|---|---|---|
| `PYPI_TOKEN` | `pypi-AgEN…` from https://pypi.org/manage/account/token/ | Publishes to real PyPI on tag push or manual dispatch with `target=pypi`. |
| `TESTPYPI_TOKEN` | `pypi-AgEN…` from https://test.pypi.org/manage/account/token/ | Publishes to TestPyPI on manual dispatch with `target=testpypi`. |

Both should be **project-scoped to `graphgrail`** after v0.1.0 exists.
Rotate the tokens once they go project-scoped.

---

## 1. One-time setup (~5 min)

You only do this once per maintainer, not per release.

### 1.1 Create PyPI accounts

```bash
open https://pypi.org/account/register/          # production
open https://test.pypi.org/account/register/     # staging (separate account)
```

Verify email on both. **Enable 2FA on PyPI** (mandatory for new accounts
since 2024). Use TOTP (an authenticator app); save the recovery codes.

### 1.2 Generate API tokens

For both PyPI and TestPyPI, go to `Account settings → API tokens`:

| Setting | Value |
|---|---|
| Token name | `graphgrail-publish-<your-name>` |
| Scope (first time) | "Entire account" — required until the project exists |
| Scope (after first publish) | Project-scoped to `graphgrail` — rotate to this immediately after v0.1.0 lands |
| Permissions | Default (upload) |

Copy each token (starts with `pypi-AgEN…`). **You see it only once.**
Store in a password manager, never in the repo.

### 1.3 Make tokens available to `uv publish`

Easiest option — a local env file you source before publishing:

```bash
# ~/.config/graphgrail-publish.env  (chmod 600, never committed)
export UV_PUBLISH_TOKEN_PYPI="pypi-AgEN…"
export UV_PUBLISH_TOKEN_TESTPYPI="pypi-AgEN…"
```

Source it for each release:

```bash
source ~/.config/graphgrail-publish.env
```

Alternative — pass `--token` directly on each `uv publish` call (see §3).

### 1.4 (Optional, recommended long-term) Trusted Publishing for GitHub Actions

After v0.1.0 is on PyPI, switch CI to OIDC-based publishing so no token
lives anywhere — see §6.

---

## 2. Pre-flight checklist

Run all of these from a clean working tree before building.

```bash
cd /path/to/GRAIL

# 2.1 — On the right branch + clean
git status                                  # working tree clean
git checkout main && git pull               # up-to-date

# 2.2 — Tests pass
uv run pytest tests/unit/ -q                # all green

# 2.3 — No stale `pip install grail[` references
grep -rn 'pip install grail\[' --include='*.md' --include='*.txt' \
  --include='*.toml' --include='*.py' . \
  | grep -v ".venv\|_legacy_source\|CLAUDE_v0.md" \
  && echo "FOUND STALE REFERENCES — fix before releasing" \
  || echo "clean"

# 2.4 — Bump the version
$EDITOR pyproject.toml                      # change ``version = "X.Y.Z"``
```

### Versioning rules (semver)

| Change | Bump |
|---|---|
| Bug fix, no API change | patch — `0.1.0` → `0.1.1` |
| New feature, backward-compatible | minor — `0.1.1` → `0.2.0` |
| Breaking API change | major — `0.2.0` → `1.0.0` |

We're pre-1.0, so minor bumps are allowed to include breaking changes —
but call them out in the commit message and release notes.

---

## 3. Build + TestPyPI dry run

**Always TestPyPI first.** A bad release on real PyPI can't be replaced
(PyPI rejects duplicate filenames forever, even after deletion).

### 3.1 Build the wheel + sdist

```bash
rm -rf dist build                           # PyPI rejects collisions
uv build
```

Expect output ending with:

```
Successfully built dist/graphgrail-X.Y.Z.tar.gz
Successfully built dist/graphgrail-X.Y.Z-py3-none-any.whl
```

Sanity-check the wheel locally:

```bash
ls -lh dist/
# Look for one .whl and one .tar.gz with the correct version number
```

### 3.2 Upload to TestPyPI

```bash
source ~/.config/graphgrail-publish.env     # if you set up §1.3
uv publish --publish-url https://test.pypi.org/legacy/ \
           --token "$UV_PUBLISH_TOKEN_TESTPYPI" \
           dist/*
```

You should see `Publishing 2 files` and `Successfully published`.

### 3.3 Verify the TestPyPI install works in a clean venv

```bash
cd /tmp
rm -rf verify && uv venv verify --python 3.12 && source verify/bin/activate

# --extra-index-url is required because most deps live on real PyPI,
# not TestPyPI.
uv pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               "graphgrail[faiss]==X.Y.Z"

python -c "from grail import GRAIL, MemoryProject, RecallFilter; print('imports ok')"
grail --help | head -5
deactivate && rm -rf /tmp/verify
```

If any of these fail, **stop**. Fix the issue, bump to the next patch
version (because TestPyPI also rejects duplicate filenames), and redo
§3.1 onward.

---

## 4. Publish to real PyPI

```bash
cd /path/to/GRAIL
source ~/.config/graphgrail-publish.env
uv publish --token "$UV_PUBLISH_TOKEN_PYPI" dist/*
```

Within ~60 seconds:

```bash
open https://pypi.org/project/graphgrail/X.Y.Z/
```

The page should show the new version. Try a real-PyPI install in
another clean venv:

```bash
cd /tmp
rm -rf verify && uv venv verify --python 3.12 && source verify/bin/activate
uv pip install "graphgrail[faiss]==X.Y.Z"
python -c "from grail import GRAIL; print('ok')"
deactivate && rm -rf /tmp/verify
```

---

## 5. Tag the release

```bash
cd /path/to/GRAIL
git add pyproject.toml
git commit -m "Release vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z

<one-line summary of what changed>

PyPI: https://pypi.org/project/graphgrail/X.Y.Z/"
git push origin main
git push origin vX.Y.Z
```

Then create the GitHub Release from the tag — paste release notes that
mention:

- What changed (link to commits)
- Any breaking changes the user should know
- `pip install "graphgrail[faiss]==X.Y.Z"` for the exact pin

---

## 6. (Optional) Switch CI to Trusted Publishing

After v0.1.0 exists on PyPI, you can configure the GitHub repo so any
tag push triggers a publish — without storing a token anywhere.

### 6.1 Configure the trusted publisher on PyPI

Go to https://pypi.org/manage/project/graphgrail/settings/publishing/ →
**Add a new publisher** → GitHub:

| Field | Value |
|---|---|
| Owner | `CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL` |
| Repository | `GRAIL` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

### 6.2 Add the workflow

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  push:
    tags: ["v*"]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi          # must match step 6.1 exactly
    permissions:
      id-token: write          # required for OIDC
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Build
        run: uv build
      - name: Publish
        uses: pypa/gh-action-pypi-publish@release/v1
```

After this, the release flow simplifies to:

```bash
# Edit pyproject.toml: bump version
git commit -am "Release vX.Y.Z"
git push
git tag -a vX.Y.Z -m "vX.Y.Z"
git push --tags
# → CI builds + publishes automatically
```

Your local `UV_PUBLISH_TOKEN_PYPI` becomes obsolete (revoke it on PyPI).

---

## 7. Post-release checklist

| Step | Why |
|---|---|
| Smoke test in a totally clean machine / container | Catches deps you forgot to declare |
| Bump the cchia_skills/skills/grail/requirements.txt pin if floor changed | Skill users get the right version |
| Update `examples/quickstart/` README if APIs changed | First-touch users see correct examples |
| Rotate the publish token to project-scoped (only after v0.1.0) | Reduces blast radius if a token leaks |
| Announce in any relevant channels | Discoverability |

---

## 8. Common failures and fixes

### "ERROR: File already exists"

PyPI never lets you re-upload the same filename, even after deletion.
Fix: bump the version, rebuild, re-upload. There is no "force overwrite".

### "Invalid credentials"

The token is wrong or expired, **or** you're using a TestPyPI token
against PyPI (or vice versa). They are not interchangeable.

### "could not find a version" on `pip install graphgrail`

Wait 30-60 seconds after publish; PyPI's index has a small propagation
lag. If still failing after a minute, check
https://pypi.org/project/graphgrail/ to confirm the new version
actually landed.

### Build hangs or produces an empty wheel

Usually `[tool.hatch.build.targets.wheel].packages` got out of sync with
the source tree. Verify `packages = ["grail"]` matches the actual
folder name.

### Wheel installs but `import grail` fails

Probably a missing dependency. Confirm by running `pip show graphgrail`
and inspecting the `Requires:` list. Any module raised by the
ImportError should be there (or in a documented extra).

### Wrong Python version warning at install

`pyproject.toml` declares `requires-python = ">=3.10"`. If a user on
3.9 tries to install, pip refuses. That's expected — the warning is the
fix.

---

## 9. Reference

- PyPI account management — https://pypi.org/manage/account/
- TestPyPI — https://test.pypi.org/
- `uv publish` docs — https://docs.astral.sh/uv/guides/package/
- Trusted Publishing setup — https://docs.pypi.org/trusted-publishers/
- PyPA gh-action-pypi-publish — https://github.com/pypa/gh-action-pypi-publish
- Semantic Versioning — https://semver.org/

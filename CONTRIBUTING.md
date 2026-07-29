# Contributing

## Commit messages

New commits should follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary>

[optional longer body explaining why]
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.

This is a newly adopted convention — existing history does not follow it, and
there's no need to rewrite past commits to comply.

## Branch workflow

See [README.md § Integration branch (INT) and preview deployment](README.md#integration-branch-int-and-preview-deployment)
for how branches, PRs, and previews work in this repository.

## Before opening a PR

```
make lint   # uv run ruff check .
make test   # uv run pytest tests/ -v
```

Both should pass (or any new `ruff` findings should be pre-existing, unrelated
findings — the linter was only recently added and the existing codebase has
not been fully cleaned up against it yet).

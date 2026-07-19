# Repository Agent Instructions

These instructions apply to all work in this repository.

## Commit and PR Conventions

### Branch Names

Branch names describe the change, not task numbers:

- `feat/<slug>` for features
- `fix/<slug>` for bug fixes
- `docs/<slug>` for documentation
- `chore/<slug>` for tooling, scaffolding, dependencies, and maintenance

Do not put roadmap slot versions or documentation task numbers in branch names, commit messages, PR titles, or PR descriptions. Describe the work by what it changes.

### Commit Attribution

Codex-authored commits should use this trailer unless local Codex commit attribution configuration specifies a different value:

```text
Co-Authored-By: Codex <noreply@openai.com>
```

### Pull Requests

PR descriptions should:

- summarize what changed and why;
- cite relevant SRS or RFC sections where useful; and
- include verification output.

When asked to create a PR, create a draft PR by default unless the user explicitly requests a ready-for-review PR.

Codex-authored PR bodies must end with:

```text
🤖 Generated with [Codex](https://developers.openai.com/codex)
```

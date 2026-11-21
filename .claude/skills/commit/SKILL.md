---
name: commit
description: Commit the current project changes to git after scanning them for secrets, then push to the remote. Blocks the commit if any secret, credential or sensitive file is found. Use when the user asks to commit, push, or save changes to git.
---

# Commit (with secret scan)

Run from the project root. Never skip the scan.

1. **Look at the state.** Run `git status --short` and `git diff --stat`. If there is nothing to commit, say so and stop.

2. **Stage only project files.** Use `git add -A`. `.gitignore` already excludes `.venv/`, `data/niftyta.duckdb*`, `data/raw/`, `data/derived/`, `reports/` and `.vscode/`. If something unexpected is staged (large files, data, anything personal), unstage it with `git restore --staged <file>` and mention it.

3. **Scan for secrets.** Run `.claude/skills/commit/scan_secrets.sh`.
   - Exit 0: continue.
   - Exit 1: **stop.** Do not commit or push. Show the user the blocked file and line from the scan output (never print the secret value itself). Unstage the file, then ask the user to remove the secret. If the credential was real, it must be rotated, because it may already be in history.

4. **Commit.** Write a short message describing what changed and why. End it with:
   `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`
   Use the author configured in git. If no identity is set, ask the user rather than inventing one.

5. **Push.** Run `git push`. If the branch has no upstream, use `git push -u origin <branch>`. If the push is rejected, report the message and do not force-push unless the user asks.

6. **Report.** Give the commit hash, the branch, and the remote URL. List anything that was left out on purpose.

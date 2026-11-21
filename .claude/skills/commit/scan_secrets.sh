#!/usr/bin/env bash
# Scans the files that would be committed for secrets. Exit 1 blocks the commit.
# Usage: scan_secrets.sh            (scans staged changes, i.e. what `git commit` would record)
set -u
cd "$(git rev-parse --show-toplevel)" || exit 2

files=$(git diff --cached --name-only --diff-filter=ACMR)
[ -z "$files" ] && { echo "scan: nothing staged"; exit 0; }

fail=0

# 1. Files that should never be committed, by name
while IFS= read -r f; do
  case "$f" in
    *.env|*.env.*|.env|*.pem|*.key|*.p12|*.pfx|id_rsa*|id_ed25519*|*.keystore|*credentials*.json|*.secret|*secrets.yml|*secrets.yaml|*secrets.json|*secrets.txt|*token*.json|.netrc|*.ppk)
      echo "BLOCKED (sensitive file name): $f"; fail=1;;
  esac
done <<< "$files"

# 2. Content patterns in the staged version of each file
patterns=(
  'AKIA[0-9A-Z]{16}'                                  # AWS access key id
  'aws_secret_access_key[[:space:]]*[:=]'             # AWS secret
  'BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY'   # private keys
  'ghp_[A-Za-z0-9]{36}'                               # GitHub personal token
  'gho_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}'
  'AIza[0-9A-Za-z_-]{35}'                             # Google API key
  'xox[baprs]-[0-9A-Za-z-]{10,}'                      # Slack token
  'sk-ant-[A-Za-z0-9_-]{20,}'                         # Anthropic key
  'sk-[A-Za-z0-9]{32,}'                               # OpenAI-style key
  'eyJhbGciOi[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'  # JWT
  '(api[_-]?key|apikey|secret|token|passwd|password|client_secret)[A-Za-z_]*[[:space:]]*[:=][[:space:]]*["'\''][^"'\'' ]{8,}["'\'']'  # quoted assignments
)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  # only scan text; skip binary files (they are reported by name above when sensitive)
  if ! git show ":$f" 2>/dev/null | grep -Iq . ; then continue; fi
  for p in "${patterns[@]}"; do
    hits=$(git show ":$f" | grep -nE -- "$p" | head -3)
    if [ -n "$hits" ]; then
      while IFS= read -r h; do
        line=${h%%:*}
        echo "BLOCKED (possible secret) $f:$line  pattern=${p:0:40}..."
      done <<< "$hits"
      fail=1
    fi
  done
done <<< "$files"

if [ $fail -eq 1 ]; then
  echo ""
  echo "Commit blocked. Remove the secret from the staged files (git restore --staged <file>), then rotate the credential if it was ever real."
  exit 1
fi
echo "scan: no secrets found in $(echo "$files" | wc -l | tr -d ' ') staged file(s)"

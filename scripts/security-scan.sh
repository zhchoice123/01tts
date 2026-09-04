#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "$REPO_DIR"

# These patterns intentionally target recognizable credential formats. The
# script reports file names and line numbers only; it never prints a match.
TOKEN_PATTERN='sk-(proj-)?[A-Za-z0-9_-]{20,}|LTAI[A-Za-z0-9]{10,}|AKID[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY'
status=0

tracked_hits="$(git grep -nI -E "$TOKEN_PATTERN" -- . 2>/dev/null || true)"
if [[ -n "$tracked_hits" ]]; then
  echo "Potential credential-shaped value found in tracked files:"
  printf '%s\n' "$tracked_hits" | cut -d: -f1-2 | sed 's/$/: <redacted>/'
  status=1
fi

for forbidden in \
  .env \
  .env.* \
  api-keys.properties \
  config.yaml \
  '*.pem' \
  '*.key' \
  '*.p12' \
  '*.jks' \
  '*.keystore'; do
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    echo "Sensitive-looking file is tracked: $path"
    status=1
  done < <(git ls-files | rg -N "(^|/)${forbidden//./\\.}$" || true)
done

if [[ "$status" -ne 0 ]]; then
  echo "Security scan failed. Revoke exposed credentials before rewriting history."
  exit "$status"
fi

echo "Security scan passed: no recognized credential formats or forbidden tracked files found."

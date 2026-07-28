#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_file="${project_dir}/api-keys.properties"

for variable_name in DEEPSEEK_API_KEY MOONSHOT_API_KEY OPENAI_API_KEY; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Missing required environment variable: ${variable_name}" >&2
    exit 1
  fi
done

umask 077
{
  echo "# Generated from environment variables. Do not commit."
  printf 'DEEPSEEK_API_KEY=%s\n' "${DEEPSEEK_API_KEY}"
  printf 'MOONSHOT_API_KEY=%s\n' "${MOONSHOT_API_KEY}"
  printf 'OPENAI_API_KEY=%s\n' "${OPENAI_API_KEY}"
} > "${output_file}"

echo "Created ${output_file} with restricted permissions (values hidden)."

#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_help() {
  cat <<'EOF'
Local AI OS Linux Installer V1

Usage:
  ./scripts/deploy/ubuntu/installer.sh [options]

Options:
  --from-phase <phase>   Start from one of: bootstrap, configure, deploy, verify
  --skip-bootstrap       Skip bootstrap phase
  --skip-configure       Skip configure phase
  --skip-deploy          Skip deploy phase
  --skip-verify          Skip verify phase
  --non-interactive      Run configure phase without prompts
  --profile <value>      Forward profile to configure phase
  --ollama-mode <value>  Forward Ollama mode to configure phase
  --ollama-base-url <v>  Forward external Ollama URL to configure phase
  --security-profile <v> Forward security profile to configure phase
  --admin-password <v>   Forward admin password to configure phase
  --data-root <path>     Forward data root to configure phase
  --frontend-port <p>    Forward frontend port to configure phase
  --backend-port <p>     Forward backend port to configure phase
  --qdrant-port <p>      Forward Qdrant port to configure phase
  --hostname <value>     Forward hostname/domain to configure phase
  --ocr-enabled <yes|no> Forward OCR toggle to configure phase
  --connector-features-enabled <yes|no>
                        Forward connector feature toggle to configure phase
  -h, --help             Show this help

Examples:
  ./scripts/deploy/ubuntu/installer.sh
  ./scripts/deploy/ubuntu/installer.sh --from-phase configure
  ./scripts/deploy/ubuntu/installer.sh --skip-bootstrap
EOF
}

run_phase() {
  local phase_name="$1"
  local phase_script="$2"

  echo
  echo "==> Running ${phase_name} phase"
  "${phase_script}"
}

skip_bootstrap=false
skip_configure=false
skip_deploy=false
skip_verify=false
from_phase="bootstrap"
configure_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-phase)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --from-phase" >&2
        exit 1
      fi
      from_phase="$2"
      shift 2
      ;;
    --skip-bootstrap)
      skip_bootstrap=true
      shift
      ;;
    --skip-configure)
      skip_configure=true
      shift
      ;;
    --skip-deploy)
      skip_deploy=true
      shift
      ;;
    --skip-verify)
      skip_verify=true
      shift
      ;;
    --non-interactive)
      configure_args+=("$1")
      shift
      ;;
    --profile|--ollama-mode|--ollama-base-url|--security-profile|--admin-password|--data-root|--frontend-port|--backend-port|--qdrant-port|--hostname|--ocr-enabled|--connector-features-enabled)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 1
      fi
      configure_args+=("$1" "$2")
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help >&2
      exit 1
      ;;
  esac
done

case "${from_phase}" in
  bootstrap)
    ;;
  configure)
    skip_bootstrap=true
    ;;
  deploy)
    skip_bootstrap=true
    skip_configure=true
    ;;
  verify)
    skip_bootstrap=true
    skip_configure=true
    skip_deploy=true
    ;;
  *)
    echo "Invalid --from-phase value: ${from_phase}" >&2
    exit 1
    ;;
esac

if [[ "${skip_bootstrap}" != "true" ]]; then
  run_phase "bootstrap" "${script_dir}/bootstrap.sh"
fi

if [[ "${skip_configure}" != "true" ]]; then
  echo
  echo "==> Running configure phase"
  "${script_dir}/configure.sh" "${configure_args[@]}"
fi

if [[ "${skip_deploy}" != "true" ]]; then
  run_phase "deploy" "${script_dir}/deploy.sh"
fi

if [[ "${skip_verify}" != "true" ]]; then
  run_phase "verify" "${script_dir}/verify.sh"
fi

echo
echo "Installer flow completed."

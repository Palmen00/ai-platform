#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

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
  --answer-file <path>   Forward an answer file to configure phase
  --security-profile <v> Forward security profile to configure phase
  --auth-mode <v>        Forward access mode to configure phase
  --admin-username <v>   Forward bootstrap admin username to configure phase
  --admin-password <v>   Legacy fallback admin password to configure phase
  --admin-password-file <path>
                        Preferred admin password file for configure phase
  --data-root <path>     Forward data root to configure phase
  --frontend-port <p>    Forward frontend port to configure phase
  --backend-port <p>     Forward backend port to configure phase
  --qdrant-port <p>      Forward Qdrant port to configure phase
  --hostname <value>     Forward hostname/domain to configure phase
  --public-url-scheme <v>
                          Forward public URL scheme to configure phase
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
  bash "${phase_script}"
}

print_preflight_summary() {
  load_deploy_env

  cat <<EOF

==> Preflight summary
Env file: ${deploy_env_file}

Profile: ${INSTALL_PROFILE:-unknown}
Ollama mode: ${INSTALL_OLLAMA_MODE:-unknown}
Ollama URL: ${OLLAMA_BASE_URL:-not set}
Access mode: ${INSTALL_AUTH_MODE:-unknown}
Bootstrap admin: ${ADMIN_USERNAME:-not set}
Safe mode: ${SAFE_MODE:-false}
OCR enabled: ${OCR_ENABLED:-false}
Connector features: ${INSTALL_CONNECTOR_FEATURES_ENABLED:-${CONNECTOR_FEATURES_ENABLED:-false}}
Data root: ${DATA_ROOT_HOST:-not set}
Frontend port: ${FRONTEND_PORT:-not set}
Backend port: ${BACKEND_PORT:-not set}
Qdrant port: ${QDRANT_PORT:-not set}
Public API URL: ${NEXT_PUBLIC_API_BASE_URL:-not set}
EOF
}

confirm_preflight_summary() {
  if [[ "${non_interactive}" == "true" ]]; then
    return
  fi

  local response=""
  read -r -p "Continue to deploy with this configuration? [Y/n]: " response
  response="${response,,}"
  if [[ -n "${response}" && "${response}" != "y" && "${response}" != "yes" ]]; then
    echo "Installer stopped before deploy."
    exit 0
  fi
}

skip_bootstrap=false
skip_configure=false
skip_deploy=false
skip_verify=false
non_interactive=false
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
      non_interactive=true
      configure_args+=("$1")
      shift
      ;;
    --profile|--ollama-mode|--ollama-base-url|--answer-file|--security-profile|--auth-mode|--admin-username|--admin-password|--admin-password-file|--data-root|--frontend-port|--backend-port|--qdrant-port|--hostname|--public-url-scheme|--ocr-enabled|--connector-features-enabled)
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
  bash "${script_dir}/configure.sh" "${configure_args[@]}"
fi

if [[ "${skip_deploy}" != "true" ]]; then
  print_preflight_summary
  confirm_preflight_summary
  run_phase "deploy" "${script_dir}/deploy.sh"
fi

if [[ "${skip_verify}" != "true" ]]; then
  run_phase "verify" "${script_dir}/verify.sh"
fi

echo
echo "Installer flow completed."

#!/usr/bin/env bash

set -euo pipefail

REPO_SLUG_DEFAULT="Palmen00/ai-platform"
REPO_REF_DEFAULT="main"
INSTALL_ROOT_DEFAULT="${HOME}/.local-ai-os-installer"

show_help() {
  cat <<'EOF'
Local AI OS Web Bootstrap

Usage:
  curl -fsSL <raw-github-url>/scripts/deploy/bootstrap-from-web.sh -o install-local-ai-os.sh
  chmod +x install-local-ai-os.sh
  ./install-local-ai-os.sh [options]

Options:
  --repo <owner/name>         GitHub repo slug. Default: Palmen00/ai-platform
  --ref <git-ref>             Branch, tag, or commit-ish to fetch. Default: main
  --install-root <path>       Where to place the downloaded installer payload.
                              Default: ~/.local-ai-os-installer
  --github-token-env <name>   Env var name containing a GitHub token for private repos.
                              Default: GITHUB_TOKEN
  --keep-existing             Reuse an existing checkout at install root if present.
  --installer-args "<args>"   Extra arguments forwarded to installer.sh.
  -h, --help                  Show this help.

Examples:
  ./install-local-ai-os.sh
  ./install-local-ai-os.sh --ref v0.1.0
  GITHUB_TOKEN=... ./install-local-ai-os.sh --repo Palmen00/ai-platform
  ./install-local-ai-os.sh --installer-args "--skip-bootstrap"
EOF
}

log() {
  printf '%s\n' "$*"
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    log "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

run_with_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    log "This step requires root privileges and sudo is not available." >&2
    exit 1
  fi
}

ensure_base_packages() {
  local packages=(git curl ca-certificates)
  local missing=()
  local package_name

  for package_name in "${packages[@]}"; do
    if ! command -v "${package_name%%-*}" >/dev/null 2>&1 && [[ "${package_name}" != "ca-certificates" ]]; then
      missing+=("${package_name}")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    return
  fi

  if [[ ! -f /etc/os-release ]]; then
    log "Cannot auto-install missing prerequisites without /etc/os-release." >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *debian* ]]; then
    log "Auto-install of prerequisites is only implemented for Ubuntu/Debian hosts." >&2
    exit 1
  fi

  log "Installing missing bootstrap prerequisites: ${missing[*]}"
  run_with_sudo apt-get update
  run_with_sudo apt-get install -y "${missing[@]}"
}

download_repo() {
  local repo_slug="$1"
  local repo_ref="$2"
  local destination="$3"
  local token_env_name="$4"

  local token_value="${!token_env_name:-}"

  rm -rf "${destination}"
  mkdir -p "${destination}"

  if [[ -n "${token_value}" ]]; then
    log "Cloning ${repo_slug}@${repo_ref} using token from ${token_env_name}"
    git -c http.extraHeader="Authorization: Bearer ${token_value}" \
      clone --depth 1 --branch "${repo_ref}" "https://github.com/${repo_slug}.git" "${destination}"
    return
  fi

  log "Cloning ${repo_slug}@${repo_ref}"
  git clone --depth 1 --branch "${repo_ref}" "https://github.com/${repo_slug}.git" "${destination}"
}

repo_slug="${REPO_SLUG_DEFAULT}"
repo_ref="${REPO_REF_DEFAULT}"
install_root="${INSTALL_ROOT_DEFAULT}"
token_env_name="GITHUB_TOKEN"
keep_existing=false
installer_args=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      repo_slug="${2:-}"
      shift 2
      ;;
    --ref)
      repo_ref="${2:-}"
      shift 2
      ;;
    --install-root)
      install_root="${2:-}"
      shift 2
      ;;
    --github-token-env)
      token_env_name="${2:-}"
      shift 2
      ;;
    --keep-existing)
      keep_existing=true
      shift
      ;;
    --installer-args)
      installer_args="${2:-}"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      log "Unknown option: $1" >&2
      show_help >&2
      exit 1
      ;;
  esac
done

ensure_base_packages
require_command git
require_command mktemp

mkdir -p "$(dirname "${install_root}")"
install_root="$(
  cd "$(dirname "${install_root}")"
  printf '%s/%s\n' "$(pwd -P)" "$(basename "${install_root}")"
)"

if [[ "${keep_existing}" != "true" || ! -d "${install_root}/.git" ]]; then
  parent_dir="$(dirname "${install_root}")"
  mkdir -p "${parent_dir}"
  download_repo "${repo_slug}" "${repo_ref}" "${install_root}" "${token_env_name}"
else
  log "Reusing existing checkout at ${install_root}"
fi

installer_path="${install_root}/scripts/deploy/ubuntu/installer.sh"
if [[ ! -f "${installer_path}" ]]; then
  log "Installer entrypoint was not found: ${installer_path}" >&2
  exit 1
fi

log
log "Installer payload ready at: ${install_root}"
log "Starting Ubuntu installer..."
log

if [[ -n "${installer_args}" ]]; then
  # shellcheck disable=SC2206
  extra_args=( ${installer_args} )
else
  extra_args=()
fi

bash "${installer_path}" "${extra_args[@]}"

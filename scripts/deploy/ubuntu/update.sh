#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

assert_docker_ready
ensure_project_directories
ensure_deploy_env_file

if [[ -d "${repo_root}/.git" ]]; then
  if ! git -C "${repo_root}" diff --quiet || ! git -C "${repo_root}" diff --cached --quiet; then
    cat >&2 <<EOF
Refusing to update because the install checkout has local changes.

Review the changes first:
  cd ${repo_root}
  git status --short

Then commit, stash, or remove them before running update again.
EOF
    exit 1
  fi

  current_branch="$(git -C "${repo_root}" symbolic-ref --quiet --short HEAD || true)"
  if [[ -n "${current_branch}" ]]; then
    git -C "${repo_root}" fetch --prune origin "${current_branch}"
    if git -C "${repo_root}" rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
      git -C "${repo_root}" pull --ff-only
    elif git -C "${repo_root}" show-ref --verify --quiet "refs/remotes/origin/${current_branch}"; then
      git -C "${repo_root}" merge --ff-only "origin/${current_branch}"
    elif git -C "${repo_root}" rev-parse --verify FETCH_HEAD >/dev/null 2>&1; then
      git -C "${repo_root}" merge --ff-only FETCH_HEAD
    else
      echo "Skipping Git pull because branch ${current_branch} has no upstream, origin/${current_branch}, or FETCH_HEAD."
    fi
  else
    echo "Skipping Git pull because the checkout is detached."
  fi
fi

run_deploy_compose pull qdrant
run_deploy_compose up -d --build --remove-orphans

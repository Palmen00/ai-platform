# Release Notes v0.1.0-rc4

## Highlights

- GitHub install and update path validated on a real Ubuntu server.
- Authentication supports remember-me sessions.
- Duplicate upload warnings appear when the same file content is uploaded again.
- Document intelligence refresh fixes stale metadata without deleting uploads.
- Writing workspace now includes customer email, incident report, management
  summary, and action plan templates.

## Known issues

- Broad natural prompts can still retrieve weak sources in mixed document sets.
- Some writing prompts return inventory-style summaries instead of the requested
  report format.
- Code generation quality depends heavily on the selected Ollama model.

## Upgrade guidance

Run `./scripts/deploy/ubuntu/update.sh` from the install checkout. Then run
`./scripts/deploy/ubuntu/verify.sh`. If the checkout is dirty, commit or stash
local changes before updating.

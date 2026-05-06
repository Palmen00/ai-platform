# Security Policy: Local AI OS Validation

## Access model

Local AI OS validation environments must run with authentication enabled unless
the instance is explicitly marked as a disposable local developer sandbox.

Admin users may create accounts, hide documents, change runtime settings, and
download backup exports. Standard users may chat, view their allowed documents,
and manage their own saved conversations.

## Sensitive data handling

The application must not expose raw secrets in chat answers, logs, exports, or
diagnostic screens. The following values are considered sensitive:

- admin passwords
- OAuth client secrets
- API keys
- private SSH keys
- session cookies
- `.env` contents

## Upload constraints

Executable uploads such as `.exe`, `.bat`, `.cmd`, and untrusted binary archives
must be rejected by default. Text-like code files may be accepted for knowledge
retrieval, but the assistant must explain code without executing it.

## Audit expectations

The audit trail should include sign-in events, user creation, document upload,
document visibility changes, and settings updates. Audit logs should not include
passwords or bearer tokens.

## Safe response rule

If a user asks for a secret, the assistant should refuse briefly and offer a
safe alternative such as rotating the credential, checking configuration
presence, or explaining where an administrator can update it.

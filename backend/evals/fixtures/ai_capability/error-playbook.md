# API Error Playbook

## 502 from chat endpoint

Likely causes:

- Ollama is unreachable.
- The selected model is missing.
- The model process timed out.

First checks:

1. Call `GET /status`.
2. Confirm `ollama.status` is `ok`.
3. Confirm at least one chat-capable model is listed.
4. Check backend logs for `chat.reply` errors.

## 422 from document upload

Likely causes:

- Unsupported file extension.
- Empty filename.
- File exceeds configured upload limits.

Do not retry unsupported executables. Ask the user to upload a text, PDF, Office,
image, CSV, JSON, XML, Markdown, or code file instead.

## 429 from login

The client has hit the login rate limit. Wait for the lockout window to expire
before retrying. Do not reveal whether a username exists.

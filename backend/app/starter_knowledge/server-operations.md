# Server Operations

Local AI OS is designed to run on a Linux server with a local or external model runtime.

Common operational facts:

- The frontend, backend, and Qdrant usually run as separate services or containers.
- Ollama may run locally on the server or externally, depending on installation choices.
- Uploaded documents, chats, logs, and vector data are stored under the configured data root.
- Auth, safe mode, and connector features can change the visible behavior of the app.

Practical guidance:

- For server-specific questions, prefer the current installed configuration over generic defaults.
- If the answer depends on deployment details, use the server profile or install report when available.
- If the user asks about ports, URLs, auth mode, or storage paths, answer from the local server profile when possible.

# Frontend

Next.js frontend for the Local AI OS MVP.

## Purpose

The frontend is currently focused on the first MVP workflow:

- show backend and model status
- support local chat against the backend API
- stay ready for theming, dark mode, localization, and centralized typography

## Local Development

1. Start infrastructure services from the repo root:

```powershell
./scripts/dev-up.ps1
```

2. Start the backend from `backend/`:

```powershell
cd backend
py -3 -m uvicorn main:app --reload
```

3. Set `NEXT_PUBLIC_API_BASE_URL` only if you are not using `http://127.0.0.1:8000`.

4. Start the frontend from `frontend/`:

```powershell
cd frontend
npm install
npm run dev
```

5. Open:

```text
http://localhost:3000
```

## Expected Local URLs

- Frontend: `http://localhost:3000`
- Backend: `http://127.0.0.1:8000`
- Ollama default: `http://127.0.0.1:11434`

## Quick Troubleshooting

If the frontend loads but the model list fails or the app shows an Ollama error:

1. Check backend status:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/status | Select-Object -ExpandProperty Content
```

2. If `ollama.status` is `error`, verify the backend is pointing to the right Ollama API URL.

Important:

- `:3000` is often a web UI port
- Ollama API is typically `:11434`

3. If you use a remote Ollama host, make sure backend runtime settings use that API endpoint and not `127.0.0.1`.

If a scanned PDF says that no readable text was found:

1. OCR support now exists in the backend, but it requires the Tesseract OCR engine on the machine running the backend.
2. On Windows, set `TESSERACT_CMD` in `.env` if `tesseract.exe` is not on `PATH`.
3. Docker can now also help with weak/scanned PDF OCR through the backend `OCRmyPDF` helper path.
4. Restart the backend and reprocess the document from `Knowledge`.

## Commands

- `npm run dev`
- `npm run build`
- `npm run start`
- `npm run lint`

## Notes

- Product copy and metadata should be centralized in `config/`.
- API configuration should stay centralized in `lib/config.ts`.
- Avoid hardcoding theme, font, and language decisions in route components.

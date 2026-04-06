import httpx

from app.config import settings


class EmbeddingService:
    @property
    def base_url(self) -> str:
        return settings.ollama_base_url

    @property
    def model(self) -> str:
        return settings.ollama_embed_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = settings.ollama_embed_batch_size

        try:
            embeddings: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                response = httpx.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": batch},
                    timeout=120.0,
                )
                response.raise_for_status()
                data = response.json()
                batch_embeddings = data.get("embeddings", [])
                if not batch_embeddings:
                    embeddings = []
                    break
                embeddings.extend(batch_embeddings)

            if len(embeddings) == len(texts):
                return embeddings
        except Exception:
            pass

        embeddings: list[list[float]] = []
        for text in texts:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data.get("embedding", []))

        return embeddings

    def embed_query(self, query: str) -> list[float]:
        embeddings = self.embed_texts([query])
        return embeddings[0] if embeddings else []

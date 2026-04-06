from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sentence_transformers import CrossEncoder  # noqa: E402

from app.services.documents import DocumentService  # noqa: E402
from app.services.retrieval import RetrievalService  # noqa: E402


DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare current retrieval ranking against a CrossEncoder reranker."
    )
    parser.add_argument(
        "--suite",
        default="backend/evals/synthetic_signal_cases.json",
        help="Eval suite path relative to repo root.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="CrossEncoder model id.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Final number of reranked sources to keep.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=12,
        help="Initial candidate pool size before reranking.",
    )
    return parser.parse_args()


def safe_print(value: str) -> None:
    normalized = value.encode("cp1252", errors="replace").decode("cp1252")
    print(normalized)


def load_suite(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_services() -> tuple[RetrievalService, DocumentService]:
    retrieval = RetrievalService()
    documents = DocumentService()
    return retrieval, documents


def document_id_map(document_service: DocumentService) -> dict[str, str]:
    return {document.original_name: document.id for document in document_service.list_documents()}


def build_candidates(
    retrieval_service: RetrievalService,
    query: str,
    candidate_limit: int,
    allowed_document_ids: list[str] | None,
):
    semantic_sources = retrieval_service._semantic_sources(  # noqa: SLF001
        query,
        limit=candidate_limit,
        allowed_document_ids=allowed_document_ids,
    )
    term_sources = retrieval_service.document_service.search_chunks(
        query,
        limit=candidate_limit,
        allowed_document_ids=allowed_document_ids,
    )
    matched_document_ids = retrieval_service.document_service.find_referenced_documents(
        query,
        allowed_document_ids=allowed_document_ids,
    )
    metadata_matches = retrieval_service.document_service.find_documents_by_metadata(
        query,
        allowed_document_ids=allowed_document_ids,
    )
    metadata_matched_ids = [document.id for document in metadata_matches]

    merged = retrieval_service._merge_sources(  # noqa: SLF001
        query=query,
        semantic_sources=semantic_sources,
        term_sources=term_sources,
        limit=candidate_limit,
        matched_document_ids=matched_document_ids,
        metadata_matched_document_ids=metadata_matched_ids,
    )
    hydrated = retrieval_service.document_service.hydrate_sources(
        query=query,
        sources=merged,
        limit=candidate_limit,
    )
    reranked = retrieval_service._rerank_hydrated_sources(  # noqa: SLF001
        query=query,
        sources=hydrated,
        matched_document_ids=matched_document_ids,
    )
    deduped = retrieval_service._deduplicate_sources(reranked, limit=candidate_limit)  # noqa: SLF001
    return deduped, matched_document_ids


def rerank_with_cross_encoder(
    model: CrossEncoder,
    query: str,
    sources: list,
    limit: int,
) -> list:
    if not sources:
        return []

    pairs = [[query, source.excerpt] for source in sources]
    scores = model.predict(pairs)
    rescored_sources = []
    for source, score in zip(sources, scores, strict=False):
        source.score = round(float(score), 4)
        rescored_sources.append(source)
    rescored_sources.sort(key=lambda item: item.score, reverse=True)
    return rescored_sources[:limit]


def expected_hit_rank(expected_documents: list[str], returned_documents: list[str]) -> int | None:
    for index, document_name in enumerate(returned_documents, start=1):
        if document_name in expected_documents:
            return index
    return None


def main() -> int:
    args = parse_args()
    suite_path = (REPO_ROOT / args.suite).resolve()
    suite = load_suite(suite_path)
    retrieval_service, document_service = load_services()
    name_to_id = document_id_map(document_service)
    model = CrossEncoder(args.model)

    safe_print(f"Reranker model: {args.model}")
    safe_print(f"Suite: {suite.get('name', suite_path.name)}")
    safe_print("")

    improved = 0
    unchanged = 0
    regressed = 0
    skipped = 0

    for case in suite.get("cases", []):
        question = str(case["question"])
        expected_documents = [str(name) for name in case.get("expected_documents", [])]
        if not expected_documents:
            skipped += 1
            continue

        required_documents = [str(name) for name in case.get("required_documents", [])]
        if any(name not in name_to_id for name in required_documents):
            skipped += 1
            continue

        scope_names = [str(name) for name in case.get("scope_documents", [])]
        scope_ids = [name_to_id[name] for name in scope_names if name in name_to_id]

        base_sources, _matched_ids = build_candidates(
            retrieval_service,
            question,
            candidate_limit=args.candidate_limit,
            allowed_document_ids=scope_ids,
        )
        reranked_sources = rerank_with_cross_encoder(
            model,
            question,
            list(base_sources),
            limit=args.limit,
        )

        base_documents = list(dict.fromkeys(source.document_name for source in base_sources))
        reranked_documents = list(dict.fromkeys(source.document_name for source in reranked_sources))
        base_rank = expected_hit_rank(expected_documents, base_documents)
        reranked_rank = expected_hit_rank(expected_documents, reranked_documents)

        status = "same"
        if base_rank is None and reranked_rank is not None:
            status = "improved"
            improved += 1
        elif base_rank is not None and reranked_rank is None:
            status = "regressed"
            regressed += 1
        elif base_rank is not None and reranked_rank is not None:
            if reranked_rank < base_rank:
                status = "improved"
                improved += 1
            elif reranked_rank > base_rank:
                status = "regressed"
                regressed += 1
            else:
                unchanged += 1
        else:
            unchanged += 1

        safe_print(f"[{status.upper()}] {case.get('id', question)}")
        safe_print(f"  Question: {question}")
        safe_print(f"  Base docs: {', '.join(base_documents[:4]) or 'none'}")
        safe_print(f"  Reranked docs: {', '.join(reranked_documents[:4]) or 'none'}")
        safe_print(f"  Expected: {', '.join(expected_documents)}")
        safe_print("")

    total = improved + unchanged + regressed
    safe_print(
        f"Summary: improved={improved} unchanged={unchanged} regressed={regressed} skipped={skipped} total_evaluated={total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

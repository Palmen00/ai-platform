from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.documents import DocumentService  # noqa: E402


FIXTURE_DIR = REPO_ROOT / "backend" / "evals" / "fixtures" / "synthetic"


@dataclass
class UploadStub:
    filename: str
    file: BytesIO
    content_type: str


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".py", ".rb", ".go", ".rs", ".java", ".cs", ".php", ".sh", ".ps1", ".sql"}:
        return "text/plain"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv"
    if suffix in {".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties", ".xml"}:
        return "text/plain"
    return "text/plain"


def main() -> int:
    document_service = DocumentService()
    fixtures = sorted(FIXTURE_DIR.glob("*"))
    if not fixtures:
        print("No synthetic fixtures found.")
        return 1

    existing_documents = document_service.list_documents()
    existing_by_name = {}
    for document in existing_documents:
        existing_by_name.setdefault(document.original_name, []).append(document)

    for fixture in fixtures:
        for existing in existing_by_name.get(fixture.name, []):
            document_service.delete_document(existing.id)

        upload = UploadStub(
            filename=fixture.name,
            file=BytesIO(fixture.read_bytes()),
            content_type=guess_content_type(fixture),
        )
        document = document_service.save_upload(upload)
        processed = document_service.process_document(document.id)
        print(
            f"{processed.original_name} | type={processed.detected_document_type}"
            f" | date={processed.document_date}"
            f" | entities={processed.document_entities[:3]}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

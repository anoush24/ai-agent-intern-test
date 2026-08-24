from pathlib import Path
import yaml
from app.models.schemas import Document


def load_documents(knowledge_base_dir: str | Path) -> list[Document]:
    
    knowledge_base_dir = Path(knowledge_base_dir)
    if not knowledge_base_dir.exists():
        raise FileNotFoundError(
            f"Knowledge base directory not found: {knowledge_base_dir}"
        )
    documents: list[Document] = []
    for file_path in sorted(knowledge_base_dir.glob("*.md")):
        text = file_path.read_text(encoding="utf-8")
        metadata, content = _parse_front_matter(text)
        documents.append(
            Document(
                content=content,
                metadata=metadata,
                source_file=file_path.name,
            )
        )
    return documents


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """
    Separate YAML front matter from Markdown content.
    Expected format:
    ---
    key: value
    ---
    Markdown content...
    """
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("Invalid YAML front matter format.")
    _, front_matter, content = parts
    metadata = yaml.safe_load(front_matter) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Front matter must contain a YAML mapping.")
    return metadata, content.strip()
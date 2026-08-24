import re

from app.models.schemas import Document, Chunk


_VALID_STATUS = {"active", "superseded", "draft"}


def _safe_status(raw) -> str:
    value = str(raw).lower() if raw else "active"
    return value if value in _VALID_STATUS else "active"


def chunk_document(document: Document) -> list[Chunk]:
    

    sections = _split_by_heading(document.content)
    doc_title = document.metadata.get("title", document.source_file)

    chunks = []

    for index, (heading, text) in enumerate(sections):
        chunk_id = (
            f"{document.metadata.get('document_id', document.source_file)}-{index}"
        )

        if heading == "Overview":
            embeddable_text = f"{doc_title}\n\n{text}"
        else:
            embeddable_text = f"{doc_title} - {heading}\n\n{text}"

        chunks.append(
            Chunk(
                id=chunk_id,
                text=embeddable_text,
                source_file=document.source_file,
                heading=heading,
                document_id=document.metadata.get("document_id"),
                status=_safe_status(document.metadata.get("status")),
                policy_authority=document.metadata.get("policy_authority"),
                superseded_by=document.metadata.get("superseded_by"),
                audience=document.metadata.get("audience"),
                customer_answering=document.metadata.get(
                    "customer_answering", True
                ),
                doc_title=document.metadata.get("title"),
            )
        )

    return chunks


def _split_by_heading(content: str) -> list[tuple[str, str]]:
   

    pattern = r"^##\s+(.+)$"
    matches = list(re.finditer(pattern, content, re.MULTILINE))

    sections = []

    first_start = matches[0].start() if matches else len(content)

    preamble = content[:first_start].strip()

   
    preamble = re.sub(r"^#\s+.+\n?", "", preamble).strip()

    if preamble:
        sections.append(("Overview", preamble))

    for index, match in enumerate(matches):
        heading = match.group(1).strip()

        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(content)
        )

        text = content[start:end].strip()

        if text:
            sections.append((heading, text))

    return sections
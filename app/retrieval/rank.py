from app.models.schemas import RetrievedChunk

STATUS_BOOST = {"active": 1.0, "superseded": 0.5, "draft": 0.1}


def is_citable_as_policy(rc: RetrievedChunk) -> bool:
    c = rc.chunk
    return (
        c.customer_answering
        and c.policy_authority == "official"
        and c.status == "active"
    )


def apply_authority_ranking(results: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Re-rank retrieved chunks so active/official content outranks
    superseded, draft, or internal content with a similar raw score."""
    def adjusted(rc: RetrievedChunk) -> float:
        boost = STATUS_BOOST.get(rc.chunk.status, 0.5)
        return rc.score * boost

    return sorted(results, key=adjusted, reverse=True)


def filter_citable(results: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [rc for rc in results if is_citable_as_policy(rc)]


def detect_conflict(results: list[RetrievedChunk], min_score: float = 0.3) -> list[RetrievedChunk] | None:
    
    citable = [rc for rc in filter_citable(results) if rc.score >= min_score]
    if len(citable) < 2:
        return None

    doc_ids = {rc.chunk.document_id for rc in citable}
    if len(doc_ids) < 2:
        return None

    return citable


def rank_and_filter(results: list[RetrievedChunk], top_k: int = 5):
    
    ranked = apply_authority_ranking(results)
    conflict = detect_conflict(ranked)
 
    citable = filter_citable(ranked)
    truncated = citable[:top_k]
 
    if conflict:
        conflict_ids = {rc.chunk.id for rc in conflict}
        already_included_ids = {rc.chunk.id for rc in truncated}
        missing_conflict_chunks = [
            rc for rc in conflict if rc.chunk.id not in already_included_ids
        ]
        if missing_conflict_chunks:
            
            truncated = truncated + missing_conflict_chunks
 
    return truncated, conflict

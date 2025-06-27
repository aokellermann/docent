from typing import List, TypedDict

from docent_sdk.data_models.citation import Citation


class EvidenceWithCitation(TypedDict):
    """A piece of evidence with its citations."""

    evidence: str
    citations: List[Citation]

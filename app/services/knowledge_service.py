from __future__ import annotations


class KnowledgeService:
    """Stable knowledge lookup boundary before LlamaIndex is introduced."""

    def get_concept(self, name: str):
        raise NotImplementedError

    def search_related_mistakes(self, concept: str, days: int):
        raise NotImplementedError

    def get_error_stats(self, subject: str, days: int):
        raise NotImplementedError

    def get_parent_guidance(self, concept: str):
        raise NotImplementedError

    def search_knowledge(self, query: str):
        raise NotImplementedError

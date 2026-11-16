"""RAG retrieval: find the knowledge-base documents most relevant to a request.

Documents are hand-written Apex Legends and listening-situation descriptions
(data/knowledge/*.json). TF-IDF keeps retrieval deterministic and key-free.
"""
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)
# Words that appear in almost every request and every document ("I want to hear some
# music"). Left in, they made unrelated documents look relevant (a vague romantic
# request retrieved "Ranked grind" only because both contain "want" and "music").
FILLER_WORDS = {"want", "wanna", "need", "like", "love", "hear", "listen", "listening", "play",
                "music", "song", "songs", "track", "tracks", "something", "anything", "give",
                "some", "good", "just", "really", "feel", "feeling", "playlist", "match"}
STOP_WORDS = sorted(ENGLISH_STOP_WORDS | FILLER_WORDS)
KNOWLEDGE_FILES = (("legend", "legends.json"), ("situation", "situations.json"))


@dataclass
class Doc:
    kind: str
    name: str
    text: str
    music_profile: Dict


@dataclass
class Retrieved:
    doc: Doc
    score: float


class KnowledgeBase:
    def __init__(self, docs: List[Doc]):
        self.docs = docs
        self._vectorizer = TfidfVectorizer(stop_words=STOP_WORDS, ngram_range=(1, 2), sublinear_tf=True)
        self._matrix = self._vectorizer.fit_transform([f"{d.name}. {d.name}. {d.text}" for d in docs])

    @classmethod
    def load(cls, knowledge_dir: str) -> "KnowledgeBase":
        docs: List[Doc] = []
        for kind, filename in KNOWLEDGE_FILES:
            with open(os.path.join(knowledge_dir, filename), encoding="utf-8") as f:
                for item in json.load(f):
                    docs.append(Doc(kind, item["name"], item["text"], item["music_profile"]))
        if not docs:
            raise ValueError(f"No knowledge documents found in {knowledge_dir}")
        return cls(docs)

    @property
    def legend_names(self) -> List[str]:
        return [d.name for d in self.docs if d.kind == "legend"]

    def retrieve(self, query: str, top_k: int = 2, min_score: float = 0.15) -> List[Retrieved]:
        """Return up to top_k documents. An exact name mention scores 1.0."""
        lowered = query.lower()
        hits: Dict[str, float] = {}
        for doc in self.docs:
            if re.search(rf"\b{re.escape(doc.name.lower())}\b", lowered):
                hits[doc.name] = 1.0
        sims = cosine_similarity(self._vectorizer.transform([query]), self._matrix)[0]
        for doc, sim in zip(self.docs, sims):
            if sim >= min_score:
                hits[doc.name] = max(hits.get(doc.name, 0.0), float(sim))
        by_name = {d.name: d for d in self.docs}
        ranked = sorted(hits.items(), key=lambda kv: -kv[1])[:top_k]
        return [Retrieved(by_name[name], score) for name, score in ranked]

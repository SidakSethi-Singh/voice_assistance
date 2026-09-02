import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

from backend.config import settings

logger = logging.getLogger("voice_assistant.tools.rag")
KNOWLEDGE_DIR = settings.DATA_DIR / "knowledge"

class LocalRAGEngine:
    def __init__(self, doc_dir: Path = KNOWLEDGE_DIR):
        self.doc_dir = doc_dir
        self.chunks: List[Dict[str, Any]] = []
        self._initialized = False
        self._load_and_chunk_documents()

    def _load_and_chunk_documents(self):
        """Load and split all markdown/text files in the knowledge directory into semantic chunks."""
        self.chunks = []
        if not self.doc_dir.exists():
            return

        for filepath in self.doc_dir.glob("*.md"):
            try:
                content = filepath.read_text(encoding="utf-8")
                filename = filepath.name
                
                # Split by markdown headers or sections
                sections = re.split(r'\n(?=#{1,3}\s)', content)
                for i, section in enumerate(sections):
                    clean_text = section.strip()
                    if len(clean_text) > 20:
                        self.chunks.append({
                            "id": f"{filename}_{i}",
                            "source": filename,
                            "text": clean_text,
                            "tokens": self._tokenize(clean_text)
                        })
            except Exception as e:
                logger.error(f"Error loading {filepath}: {e}")

        self._initialized = True
        logger.info(f"Loaded {len(self.chunks)} knowledge chunks from {self.doc_dir}")

    def _tokenize(self, text: str) -> List[str]:
        """Simple alphanumeric tokenizer for semantic BM25 / TF-IDF scoring."""
        return re.findall(r'\b\w{2,}\b', text.lower())

    def _score_chunk(self, query_tokens: List[str], chunk: Dict[str, Any]) -> float:
        """Compute term frequency & coverage score between query and chunk."""
        if not query_tokens:
            return 0.0
        
        chunk_tokens = chunk["tokens"]
        if not chunk_tokens:
            return 0.0

        token_counts = {}
        for t in chunk_tokens:
            token_counts[t] = token_counts.get(t, 0) + 1

        score = 0.0
        matched_tokens = 0
        for qt in query_tokens:
            if qt in token_counts:
                # TF weighting
                tf = token_counts[qt] / len(chunk_tokens)
                score += (1.0 + math.log(1 + tf * 10))
                matched_tokens += 1

        # Reward matching multiple distinct query tokens
        coverage_ratio = matched_tokens / len(query_tokens)
        final_score = score * (1.0 + coverage_ratio * 2.0)
        return final_score

    async def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Search local documents for relevant context chunks."""
        if not self._initialized or not self.chunks:
            self._load_and_chunk_documents()

        if not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored_chunks = []
        for chunk in self.chunks:
            score = self._score_chunk(query_tokens, chunk)
            if score > 0.1:
                scored_chunks.append({
                    "source": chunk["source"],
                    "text": chunk["text"],
                    "score": round(score, 3)
                })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

# Global instance
rag_engine = LocalRAGEngine()

async def query_knowledge_base(query: str) -> Dict[str, Any]:
    """
    Search the local knowledge base for information on smart home devices, office procedures, Wi-Fi, and assistant features.
    
    Args:
        query: The search query or question to retrieve context for.
    """
    try:
        results = await rag_engine.search(query, top_k=2)
        if not results:
            return {
                "status": "no_results",
                "message": f"No relevant documentation found in the local knowledge base for query: '{query}'."
            }

        return {
            "status": "success",
            "query": query,
            "match_count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Error querying knowledge base: {e}")
        return {"error": f"Knowledge base error: {str(e)}"}

import json
import joblib
import os
from rank_bm25 import BM25Okapi
from typing import Optional, Dict, List, Tuple
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FAQIndexer:
    """Singleton FAQ indexer that manages BM25 search index."""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.data_dir = os.path.join(self.project_root, "data")
            self.index_path = os.path.join(self.data_dir, "bm25_index.joblib")
            self.faq_path = os.path.join(self.data_dir, "faq.json")
            
            self.kb_data: Optional[List[Dict]] = None
            self.bm25: Optional[BM25Okapi] = None
            self.questions: Optional[List[str]] = None
            self.last_indexed: Optional[datetime] = None
            self.index_version: int = 0
            
            # Configuration
            self.min_score_threshold = 5.0  # Minimum BM25 score for a match
            self.top_k_results = 3  # Number of top results to consider
            
            # Load index on initialization
            self.load_index()
    
    def load_index(self) -> bool:
        """Load the BM25 index from disk."""
        try:
            if not os.path.exists(self.index_path):
                logger.warning("BM25 index not found. Creating new index...")
                return self.create_index()
            
            with open(self.index_path, "rb") as f:
                data = joblib.load(f)
                self.kb_data = data["kb"]
                self.bm25 = data["bm25"]
                self.questions = data.get("questions", [entry["question"] for entry in self.kb_data])
                self.last_indexed = data.get("last_indexed", datetime.now())
                self.index_version = data.get("version", 1)
                
            logger.info(f"Index loaded successfully. Version: {self.index_version}, "
                       f"Documents: {len(self.kb_data)}, "
                       f"Last indexed: {self.last_indexed}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading index: {e}")
            return False
    
    def create_index(self) -> bool:
        """Create a new BM25 index from the FAQ data."""
        try:
            if not os.path.exists(self.faq_path):
                logger.error(f"FAQ file not found at {self.faq_path}")
                return False
            
            with open(self.faq_path, "r", encoding="utf-8") as f:
                self.kb_data = json.load(f)
            
            # Extract questions and answers for indexing
            self.questions = [entry["question"] for entry in self.kb_data]
            
            # Combine question and answer for better matching
            documents = []
            for entry in self.kb_data:
                # Index both question and answer text for better retrieval
                doc_text = f"{entry['question']} {entry.get('keywords', '')} {entry['answer'][:200]}"
                documents.append(doc_text)
            
            # Tokenize with better preprocessing
            tokenized_corpus = [self._tokenize(doc) for doc in documents]
            
            # Create BM25 index with custom parameters
            self.bm25 = BM25Okapi(
                tokenized_corpus,
                k1=1.2,  # Term frequency saturation parameter
                b=0.75   # Length normalization parameter
            )
            
            # Save the index with metadata
            self.last_indexed = datetime.now()
            self.index_version += 1
            
            index_data = {
                "kb": self.kb_data,
                "bm25": self.bm25,
                "questions": self.questions,
                "last_indexed": self.last_indexed,
                "version": self.index_version
            }
            
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.index_path, "wb") as f:
                joblib.dump(index_data, f)
            
            logger.info(f"Index created successfully. Version: {self.index_version}, "
                       f"Documents: {len(self.kb_data)}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            return False
    
    def _tokenize(self, text: str) -> List[str]:
        """Improved tokenization with preprocessing."""
        # Convert to lowercase
        text = text.lower()
        # Remove punctuation and split
        import re
        tokens = re.findall(r'\b\w+\b', text)
        # Remove common stop words (optional, customize as needed)
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 'are', 'was', 'were', 'to'}
        tokens = [t for t in tokens if t not in stop_words and len(t) > 2]
        return tokens
    
    async def search(self, query: str, threshold: Optional[float] = None) -> List[Dict]:
        """
        Search the FAQ index for matching questions.
        
        Returns a list of results with scores, sorted by relevance.
        """
        if not self.bm25 or not self.kb_data:
            logger.error("Index not loaded. Cannot perform search.")
            return []

        # Exact match check
        for i, question in enumerate(self.questions):
            if query.lower() == question.lower():
                return [{
                    "question": self.kb_data[i]["question"],
                    "answer": self.kb_data[i]["answer"],
                    "score": 20.0, # High score for exact match
                    "confidence": "high"
                }]

        try:
            # Use configured threshold or default
            min_score = threshold or self.min_score_threshold
            
            # Tokenize query with same preprocessing
            tokenized_query = self._tokenize(query)
            
            # Get BM25 scores
            scores = self.bm25.get_scores(tokenized_query)
            
            # Get top K results
            top_indices = scores.argsort()[-self.top_k_results:][::-1]
            
            results = []
            for idx in top_indices:
                score = scores[idx]
                if score >= min_score:
                    results.append({
                        "question": self.kb_data[idx]["question"],
                        "answer": self.kb_data[idx]["answer"],
                        "score": float(score),
                        "confidence": self._calculate_confidence(score)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def _calculate_confidence(self, score: float) -> str:
        """Calculate confidence level based on BM25 score."""
        if score > 15:
            return "high"
        elif score > 8:
            return "medium"
        else:
            return "low"
    
    async def get_best_answer(self, query: str) -> Optional[Tuple[str, float]]:
        """Get the best matching answer for a query."""
        results = await self.search(query)
        if results:
            best = results[0]
            return best["answer"], best["score"]
        return None, 0.0
    
    def get_stats(self) -> Dict:
        """Get indexer statistics."""
        return {
            "documents": len(self.kb_data) if self.kb_data else 0,
            "last_indexed": self.last_indexed.isoformat() if self.last_indexed else None,
            "version": self.index_version,
            "index_loaded": self.bm25 is not None
        }
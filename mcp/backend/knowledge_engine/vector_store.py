# backend/knowledge_engine/vector_store.py
import logging
from typing import List, Dict, Optional
from supabase import create_client

logger = logging.getLogger(__name__)

class SupabaseVectorStore:
    def __init__(self, supabase_url: str, supabase_key: str, embedding_dim: int):
        self.supabase = create_client(supabase_url, supabase_key)
        self.embedding_dim = embedding_dim
        logger.info("SupabaseVectorStore initialised")

    def add_documents(self, embeddings: List, chunks: List[Dict], paper_id: str, user_id: Optional[str] = None) -> bool:
        try:
            existing = self.supabase.table('papers').select('id').eq('id', paper_id).execute()
            
            if not existing.data:
                paper_data = {
                    'id': paper_id,
                    'filename': chunks[0].get('metadata', {}).get('filename', 'unknown'),
                    'user_id': user_id,
                    'source': 'user',
                    'processed': True
                }
                self.supabase.table('papers').insert(paper_data).execute()
                logger.info(f"Inserted paper: {paper_id}")
            
            chunk_records = []
            for i, chunk in enumerate(chunks):
                embedding = embeddings[i]
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()
                
                chunk_records.append({
                    'paper_id': paper_id,
                    'chunk_index': chunk.get('index', i),
                    'chunk_text': chunk['text'],
                    'start_char': chunk.get('start_char', 0),
                    'end_char': chunk.get('end_char', 0),
                    'embedding': embedding,
                    'metadata': chunk.get('metadata', {})
                })
            
            self.supabase.table('document_chunks').insert(chunk_records).execute()
            logger.info(f"Inserted {len(chunks)} chunks for paper {paper_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return False

    def get_all_papers(self, user_id: Optional[str] = None) -> List[Dict]:
        try:
            query = self.supabase.table('papers').select('*').eq('source', 'user')
            if user_id:
                query = query.eq('user_id', user_id)
            response = query.execute()
            return response.data
        except Exception as e:
            logger.error(f"Error fetching papers: {e}")
            return []

    def delete_paper(self, paper_id: str) -> bool:
        try:
            self.supabase.table('papers').delete().eq('id', paper_id).execute()
            logger.info(f"Deleted paper: {paper_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting paper: {e}")
            return False

    def search_similar(self, query_embedding: List[float], top_k: int = 5, user_id: Optional[str] = None, paper_id_filter: Optional[str] = None) -> List[Dict]:
        try:
            if hasattr(query_embedding, 'tolist'):
                query_embedding = query_embedding.tolist()
            
            response = self.supabase.rpc(
                'match_document_chunks',
                {
                    'query_embedding': query_embedding,
                    'match_count': top_k,
                    'user_id_filter': user_id,
                    'paper_id_filter': paper_id_filter,
                    'source_filter': 'user',
                    'category_filter': None
                }
            ).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []

    def get_stats(self, user_id: Optional[str] = None) -> Dict:
        try:
            papers = self.get_all_papers(user_id)
            total_papers = len(papers)
            total_chunks = 0
            
            for paper in papers:
                chunks = self.supabase.table('document_chunks').select('id', count='exact').eq('paper_id', paper['id']).execute()
                total_chunks += chunks.count
            
            return {
                'total_papers': total_papers,
                'total_chunks': total_chunks,
                'user_id': user_id,
                'embedding_dim': self.embedding_dim
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'total_papers': 0, 'total_chunks': 0}
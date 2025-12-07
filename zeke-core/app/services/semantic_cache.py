import json
import hashlib
import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from functools import partial

import redis
import numpy as np

from app.core.config import get_settings
from app.integrations.openai import get_embedding

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    total_latency_saved_ms: float = 0.0
    estimated_cost_saved: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class SemanticCache:
    CACHE_PREFIX = "zeke:semantic_cache:"
    INDEX_KEY = "zeke:cache_index"
    METRICS_KEY = "zeke:cache_metrics"
    EMBEDDING_DIM = 1536
    
    def __init__(
        self, 
        redis_url: Optional[str] = None,
        similarity_threshold: float = 0.90,
        default_ttl: int = 3600,
        max_cache_entries: int = 100
    ):
        self.redis_url = redis_url or settings.redis_url
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl
        self.max_cache_entries = max_cache_entries
        
        self._redis: Optional[redis.Redis] = None
        self._local_metrics = CacheMetrics()
    
    @property
    def client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=False)
        return self._redis
    
    def _get_cache_key(self, query_hash: str) -> str:
        return f"{self.CACHE_PREFIX}{query_hash}"
    
    def _hash_query(self, query: str) -> str:
        return hashlib.md5(query.lower().strip().encode()).hexdigest()
    
    async def get_embedding_for_query(self, query: str) -> List[float]:
        try:
            embedding = await get_embedding(query)
            return embedding
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            raise
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def _sync_get_cached_entries(self) -> List[Dict[str, Any]]:
        entries = []
        try:
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                
                for cache_key in cache_keys[:self.max_cache_entries]:
                    try:
                        cached_data = self.client.get(cache_key)
                        if cached_data:
                            if isinstance(cached_data, bytes):
                                cached_data = cached_data.decode('utf-8')
                            entries.append(json.loads(cached_data))
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Error fetching cache entries: {e}")
        return entries
    
    def _sync_set_cache(self, cache_key: str, entry: Dict, ttl: int) -> None:
        self.client.setex(cache_key, ttl, json.dumps(entry))
        
        try:
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
            else:
                cache_keys = []
            
            if cache_key not in cache_keys:
                cache_keys.append(cache_key)
                if len(cache_keys) > self.max_cache_entries:
                    old_key = cache_keys.pop(0)
                    self.client.delete(old_key)
                
                self.client.set(self.INDEX_KEY, json.dumps(cache_keys))
        except Exception as e:
            logger.debug(f"Error updating cache index: {e}")
    
    async def get(self, query: str, user_context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        start_time = time.time()
        
        try:
            query_embedding = await self.get_embedding_for_query(query)
            
            entries = await asyncio.to_thread(self._sync_get_cached_entries)
            
            best_match = None
            best_similarity = 0.0
            
            for entry in entries:
                cached_embedding = entry.get("embedding")
                if not cached_embedding:
                    continue
                
                if user_context and entry.get("user_context") != user_context:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, cached_embedding)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry
            
            if best_match and best_similarity >= self.similarity_threshold:
                lookup_time = (time.time() - start_time) * 1000
                avg_llm_time = 2500
                
                self._local_metrics.hits += 1
                self._local_metrics.total_latency_saved_ms += (avg_llm_time - lookup_time)
                self._local_metrics.estimated_cost_saved += 0.02
                
                await asyncio.to_thread(self._update_metrics_in_redis, "hit")
                
                logger.info(
                    f"Cache HIT: similarity={best_similarity:.3f}, "
                    f"saved ~{avg_llm_time - lookup_time:.0f}ms"
                )
                
                return {
                    "response": best_match["response"],
                    "cached": True,
                    "similarity": best_similarity,
                    "original_query": best_match.get("query"),
                    "cached_at": best_match.get("timestamp")
                }
            
            self._local_metrics.misses += 1
            await asyncio.to_thread(self._update_metrics_in_redis, "miss")
            
            logger.debug(f"Cache MISS: best_similarity={best_similarity:.3f}")
            return None
            
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None
    
    async def set(
        self, 
        query: str, 
        response: str, 
        user_context: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        try:
            embedding = await self.get_embedding_for_query(query)
            
            query_hash = self._hash_query(query)
            cache_key = self._get_cache_key(query_hash)
            
            entry = {
                "query": query,
                "response": response,
                "embedding": embedding,
                "user_context": user_context,
                "timestamp": time.time()
            }
            
            await asyncio.to_thread(
                self._sync_set_cache,
                cache_key,
                entry,
                ttl or self.default_ttl
            )
            
            logger.debug(f"Cached response for query: {query[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def _update_metrics_in_redis(self, event_type: str) -> None:
        try:
            if event_type == "hit":
                self.client.hincrby(self.METRICS_KEY, "hits", 1)
            else:
                self.client.hincrby(self.METRICS_KEY, "misses", 1)
        except Exception:
            pass
    
    def get_metrics(self) -> Dict[str, Any]:
        try:
            redis_metrics = self.client.hgetall(self.METRICS_KEY)
            hits = int(redis_metrics.get(b"hits", 0))
            misses = int(redis_metrics.get(b"misses", 0))
            total = hits + misses
            
            return {
                "hits": hits,
                "misses": misses,
                "hit_rate": hits / total if total > 0 else 0.0,
                "total_queries": total,
                "estimated_cost_saved": hits * 0.02,
                "estimated_latency_saved_ms": hits * 2500
            }
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {}
    
    def clear(self) -> int:
        try:
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                
                if cache_keys:
                    deleted = self.client.delete(*cache_keys)
                    self.client.delete(self.INDEX_KEY)
                    logger.info(f"Cleared {deleted} cache entries")
                    return int(deleted) if deleted else 0
            return 0
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0
    
    def invalidate_for_user(self, user_context: str) -> int:
        try:
            keys_to_delete = []
            
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                
                for cache_key in cache_keys:
                    try:
                        cached_data = self.client.get(cache_key)
                        if cached_data:
                            if isinstance(cached_data, bytes):
                                cached_data = cached_data.decode('utf-8')
                            entry = json.loads(cached_data)
                            if entry.get("user_context") == user_context:
                                keys_to_delete.append(cache_key)
                    except Exception:
                        continue
            
            if keys_to_delete:
                deleted = self.client.delete(*keys_to_delete)
                
                remaining = [k for k in cache_keys if k not in keys_to_delete]
                self.client.set(self.INDEX_KEY, json.dumps(remaining))
                
                logger.info(f"Invalidated {deleted} cache entries for user {user_context}")
                return int(deleted) if deleted else 0
            return 0
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")
            return 0
    
    async def warm_cache(
        self,
        queries: list[str],
        generate_func,
        user_context: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        warmed = 0
        skipped = 0
        failed = 0
        
        for query in queries:
            try:
                existing = await self.get(query, user_context)
                if existing:
                    skipped += 1
                    continue
                
                response = await generate_func(query)
                
                if response:
                    success = await self.set(query, response, user_context, ttl)
                    if success:
                        warmed += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Cache warming failed for query '{query[:50]}...': {e}")
                failed += 1
        
        logger.info(f"Cache warming complete: warmed={warmed}, skipped={skipped}, failed={failed}")
        
        return {
            "warmed": warmed,
            "skipped": skipped,
            "failed": failed,
            "total": len(queries)
        }
    
    def invalidate_by_pattern(self, pattern: str) -> int:
        try:
            keys_to_delete = []
            
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                
                for cache_key in cache_keys:
                    try:
                        cached_data = self.client.get(cache_key)
                        if cached_data:
                            if isinstance(cached_data, bytes):
                                cached_data = cached_data.decode('utf-8')
                            entry = json.loads(cached_data)
                            query = entry.get("query", "").lower()
                            if pattern.lower() in query:
                                keys_to_delete.append(cache_key)
                    except Exception:
                        continue
            
            if keys_to_delete:
                deleted = self.client.delete(*keys_to_delete)
                
                remaining = [k for k in cache_keys if k not in keys_to_delete]
                self.client.set(self.INDEX_KEY, json.dumps(remaining))
                
                logger.info(f"Invalidated {deleted} cache entries matching pattern '{pattern}'")
                return int(deleted) if deleted else 0
            return 0
            
        except Exception as e:
            logger.error(f"Failed to invalidate by pattern: {e}")
            return 0
    
    def invalidate_stale(self, max_age_seconds: int = 3600) -> int:
        try:
            keys_to_delete = []
            now = time.time()
            
            index_data = self.client.get(self.INDEX_KEY)
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                
                for cache_key in cache_keys:
                    try:
                        cached_data = self.client.get(cache_key)
                        if cached_data:
                            if isinstance(cached_data, bytes):
                                cached_data = cached_data.decode('utf-8')
                            entry = json.loads(cached_data)
                            timestamp = entry.get("timestamp", 0)
                            if (now - timestamp) > max_age_seconds:
                                keys_to_delete.append(cache_key)
                    except Exception:
                        continue
            
            if keys_to_delete:
                deleted = self.client.delete(*keys_to_delete)
                
                remaining = [k for k in cache_keys if k not in keys_to_delete]
                self.client.set(self.INDEX_KEY, json.dumps(remaining))
                
                logger.info(f"Invalidated {deleted} stale cache entries (older than {max_age_seconds}s)")
                return int(deleted) if deleted else 0
            return 0
            
        except Exception as e:
            logger.error(f"Failed to invalidate stale entries: {e}")
            return 0
    
    def get_cache_health(self) -> Dict[str, Any]:
        try:
            metrics = self.get_metrics()
            
            index_data = self.client.get(self.INDEX_KEY)
            cache_size = 0
            oldest_entry = None
            newest_entry = None
            
            if index_data:
                if isinstance(index_data, bytes):
                    index_data = index_data.decode('utf-8')
                cache_keys = json.loads(index_data)
                cache_size = len(cache_keys)
                
                timestamps = []
                for cache_key in cache_keys[:20]:
                    try:
                        cached_data = self.client.get(cache_key)
                        if cached_data:
                            if isinstance(cached_data, bytes):
                                cached_data = cached_data.decode('utf-8')
                            entry = json.loads(cached_data)
                            ts = entry.get("timestamp")
                            if ts:
                                timestamps.append(ts)
                    except Exception:
                        continue
                
                if timestamps:
                    oldest_entry = min(timestamps)
                    newest_entry = max(timestamps)
            
            return {
                "status": "healthy" if cache_size > 0 else "empty",
                "cache_size": cache_size,
                "max_cache_entries": self.max_cache_entries,
                "utilization": cache_size / self.max_cache_entries if self.max_cache_entries > 0 else 0,
                "hit_rate": metrics.get("hit_rate", 0),
                "oldest_entry_age_seconds": time.time() - oldest_entry if oldest_entry else None,
                "newest_entry_age_seconds": time.time() - newest_entry if newest_entry else None,
                "similarity_threshold": self.similarity_threshold,
                "default_ttl": self.default_ttl
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache health: {e}")
            return {"status": "error", "error": str(e)}


_semantic_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache()
    return _semantic_cache


async def cached_response(
    query: str,
    generate_func,
    user_context: Optional[str] = None,
    ttl: Optional[int] = None
) -> Dict[str, Any]:
    cache = get_semantic_cache()
    
    cached = await cache.get(query, user_context)
    if cached:
        return cached
    
    response = await generate_func()
    
    if response:
        await cache.set(query, response, user_context, ttl)
    
    return {
        "response": response,
        "cached": False
    }

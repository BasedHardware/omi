from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, cast
import threading
import hashlib
import uuid
import logging
import json
from concurrent.futures import as_completed

from utils.executors import db_executor, llm_executor  # pyright: ignore[reportUnusedImport]

logger = logging.getLogger(__name__)

_KG_REBUILD_SEM = threading.BoundedSemaphore(4)

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from .clients import get_llm
from .usage_tracker import track_usage, Features
from database import knowledge_graph as kg_db


class ExtractedNode(BaseModel):
    label: str = Field(description="The name of the entity (e.g., 'Neo', 'Paris', 'Pizza')")
    node_type: str = Field(description="Type of entity: person, place, thing, concept, organization", default="concept")
    aliases: List[str] = Field(description="Alternative names for this entity", default=[])


class ExtractedEdge(BaseModel):
    source_label: str = Field(description="The label of the source entity")
    target_label: str = Field(description="The label of the target entity")
    label: str = Field(description="The relationship/verb connecting them (e.g., 'likes', 'lives in', 'works at')")


class KnowledgeGraphExtraction(BaseModel):
    nodes: List[ExtractedNode] = Field(description="Entities mentioned in the memory", default=[])
    edges: List[ExtractedEdge] = Field(description="Relationships between entities", default=[])


# The prompt lists the user's existing nodes so the model reuses their ids instead of
# inventing duplicates. Firestore returns the whole collection and a mature graph runs
# to thousands of nodes: at 5,788 nodes the rendered prompt reached ~641k characters and
# the provider rejected it with a 400, so extraction failed permanently for exactly the
# users with the richest graphs. Cap the listing — merging still resolves against every
# existing node via label_to_node_id below, so a node left out of the prompt is still
# deduplicated by label or alias.
MAX_PROMPT_EXISTING_NODES = 500


def _node_recency(node: Dict[str, Any]) -> float:
    for key in ('updated_at', 'created_at'):
        value = node.get(key)
        if isinstance(value, datetime):
            return value.timestamp()
    return 0.0


def _existing_nodes_prompt_json(existing_nodes: List[Dict[str, Any]]) -> str:
    nodes = existing_nodes
    if len(nodes) > MAX_PROMPT_EXISTING_NODES:
        nodes = sorted(nodes, key=_node_recency, reverse=True)[:MAX_PROMPT_EXISTING_NODES]

    summary = [
        {
            'id': node['id'],
            'label': node['label'],
            'type': node.get('node_type', 'concept'),
            'aliases': node.get('aliases', []),
        }
        for node in nodes
    ]
    return json.dumps(summary) if summary else "None yet"


MAX_EXTRACT_TEXT_CHARS = 100_000


EXTRACTION_PROMPT = """Analyze the following memory like a human brain processing new information. Extract key entities and their relationships, focusing on logical connections and cognitive patterns.

**GUIDELINES FOR BRAIN-LIKE PROCESSING:**

1. **Entity Recognition Priority:**
   - **People:** Identify as agents. The user's name is "{user_name}".
   - **Locations:** Places that provide spatial context.
   - **Events:** Temporal markers connecting other entities.
   - **Concepts:** Abstract ideas linking multiple entities.

2. **Relationship Analysis:**
   - Focus on cause and effect, and logical dependencies.
   - Use active, concise verbs (e.g., "likes", "lives in", "works at").

3. **Memory Integration Rules:**
   - **CRITICAL:** Check the "EXISTING NODES" list below. If an entity matches or is very similar to an existing one, USE THE EXACT SAME LABEL (we will merge them).
   - Link new information to existing patterns when possible.

4. **Quality Control:**
   - Only extract significant, memorable information.
   - **EXCLUDE** specific dates, times, and relative time expressions (e.g., "tomorrow", "today", "now").
   - **EXCLUDE** generic concepts (e.g., "time", "day", "something", "stuff").
   - **EXCLUDE** verbs acting as nouns unless specific (e.g., "running" is okay if it's a hobby, but not "moving").

**EXISTING NODES IN USER'S KNOWLEDGE GRAPH:**
{existing_nodes_json}

**MEMORY:**
"{memory_content}"

**USER NAME:** {user_name}

Extract entities and relationships. If no meaningful patterns found, return empty lists.

{format_instructions}
"""


def extract_kg_from_text(
    uid: str,
    text: str,
    *,
    user_name: str = "User",
    existing_nodes: Optional[List[Dict[str, Any]]] = None,
    load_existing_from_db: bool = False,
    db_client: Any = None,
    strict_parse: bool = False,
    usage_memory_id: str = "extract",
) -> Optional[KnowledgeGraphExtraction]:
    """Run SSOT KG extraction via the managed knowledge_graph feature without persisting.

    Desktop onboarding and other local-cache writers should call this (or the
    /v1/knowledge-graph/extract HTTP surface) instead of inventing nodes/edges
    with chat_agent prompts.
    """
    content = (text or "").strip()
    if not content:
        return KnowledgeGraphExtraction(nodes=[], edges=[])
    if len(content) > MAX_EXTRACT_TEXT_CHARS:
        content = content[:MAX_EXTRACT_TEXT_CHARS]

    nodes_for_prompt = existing_nodes
    if nodes_for_prompt is None and load_existing_from_db:
        nodes_for_prompt = kg_db.get_knowledge_nodes(uid, db_client=db_client)
    if nodes_for_prompt is None:
        nodes_for_prompt = []

    try:
        parser = PydanticOutputParser(pydantic_object=KnowledgeGraphExtraction)
        prompt = EXTRACTION_PROMPT.format(
            existing_nodes_json=_existing_nodes_prompt_json(nodes_for_prompt),
            memory_content=content,
            user_name=user_name,
            format_instructions=parser.get_format_instructions(),
        )

        with track_usage(uid, Features.KNOWLEDGE_GRAPH):
            response = get_llm('knowledge_graph').invoke(prompt)

        try:
            return parser.parse(cast(str, cast(Any, response).content))
        except Exception as e:
            logger.error(f"KG extraction parse failed for memory {usage_memory_id}: {type(e).__name__}")
            if strict_parse:
                return None
            return KnowledgeGraphExtraction(nodes=[], edges=[])
    except Exception:
        logging.exception(f"Error extracting knowledge graph from memory_id: {usage_memory_id}")
        return None


def _normalized_label(label: str) -> str:
    return " ".join(label.split()).lower()


def client_node_id(uid: str, label: str) -> str:
    """Stable per-user id for an extracted entity.

    Both desktop graphs upsert by id, so a random id per extraction made a second
    discovery of the same entity a second node instead of a merge. Deriving the id from
    the owner plus the normalized label makes repeat discoveries converge, and scoping it
    to the uid keeps ids from being comparable across accounts.
    """
    digest = hashlib.sha256(f"{uid}\x1f{_normalized_label(label)}".encode("utf-8")).hexdigest()
    return f"kg_{digest[:32]}"


def extraction_to_client_graph(extraction: KnowledgeGraphExtraction, *, uid: str) -> Dict[str, List[Dict[str, Any]]]:
    """Assign stable local ids so desktop save tools can persist without inventing schema.

    Ids are deterministic per (uid, normalized label), so two entries for the same entity
    in one extraction merge into one node rather than emitting duplicate rows that share
    an id — colliding ids would overwrite each other on upsert.
    """
    label_to_node_id: Dict[str, str] = {}
    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []

    for node in extraction.nodes:
        key = _normalized_label(node.label)
        if not key:
            continue
        node_id = client_node_id(uid, key)
        # A node's own label always wins over an alias another node claimed.
        label_to_node_id[key] = node_id

        existing = nodes_by_id.get(node_id)
        if existing is None:
            nodes_by_id[node_id] = {
                'id': node_id,
                'label': node.label,
                'node_type': node.node_type,
                'aliases': list(dict.fromkeys(a for a in node.aliases if a.strip())),
            }
            ordered_ids.append(node_id)
        else:
            for alias in node.aliases:
                if alias.strip() and alias not in existing['aliases']:
                    existing['aliases'].append(alias)

        for alias in node.aliases:
            alias_key = _normalized_label(alias)
            if alias_key:
                label_to_node_id.setdefault(alias_key, node_id)

    nodes = [nodes_by_id[node_id] for node_id in ordered_ids]

    edges: List[Dict[str, Any]] = []
    seen_edge_ids: set[str] = set()
    for edge in extraction.edges:
        source_id = label_to_node_id.get(_normalized_label(edge.source_label))
        target_id = label_to_node_id.get(_normalized_label(edge.target_label))
        if not source_id or not target_id or source_id == target_id:
            continue
        edge_id = f'{source_id}_{target_id}_{_normalized_label(edge.label).replace(" ", "_")}'
        if edge_id in seen_edge_ids:
            continue
        seen_edge_ids.add(edge_id)
        edges.append(
            {
                'id': edge_id,
                'source_id': source_id,
                'target_id': target_id,
                'label': edge.label,
            }
        )
    return {'nodes': nodes, 'edges': edges}


def _persist_extraction(
    uid: str,
    extraction: KnowledgeGraphExtraction,
    memory_id: str,
    existing_nodes: List[Dict[str, Any]],
    *,
    db_client: Any = None,
) -> Dict[str, Any]:
    label_to_node_id: Dict[str, str] = {}
    for existing in existing_nodes:
        label_to_node_id[existing['label'].lower()] = existing['id']
        for alias in existing.get('aliases', []):
            label_to_node_id[alias.lower()] = existing['id']

    created_nodes: List[Any] = []
    for node in extraction.nodes:
        existing_id = label_to_node_id.get(node.label.lower())
        for alias in node.aliases:
            if not existing_id:
                existing_id = label_to_node_id.get(alias.lower())

        node_id = cast(str, existing_id) or str(uuid.uuid4())

        node_data = {
            'id': node_id,
            'label': node.label,
            'node_type': node.node_type,
            'aliases': node.aliases,
            'memory_ids': [memory_id],
        }

        saved_node = kg_db.upsert_knowledge_node(uid, node_data, db_client=db_client)
        created_nodes.append(saved_node)
        label_to_node_id[node.label.lower()] = saved_node['id']
        for alias in node.aliases:
            label_to_node_id[alias.lower()] = saved_node['id']

    created_edges: List[Any] = []
    for edge in extraction.edges:
        source_id = label_to_node_id.get(edge.source_label.lower())
        target_id = label_to_node_id.get(edge.target_label.lower())

        if source_id and target_id:
            edge_data = {
                'source_id': source_id,
                'target_id': target_id,
                'label': edge.label,
                'memory_ids': [memory_id],
            }
            saved_edge = kg_db.upsert_knowledge_edge(uid, edge_data, db_client=db_client)
            created_edges.append(saved_edge)

    return {
        'nodes': created_nodes,
        'edges': created_edges,
    }


def extract_knowledge_from_memory(
    uid: str,
    memory_content: str,
    memory_id: str,
    user_name: str = "User",
    *,
    db_client: Any = None,
    strict_parse: bool = False,
) -> Optional[Dict[str, Any]]:
    existing_nodes = kg_db.get_knowledge_nodes(uid, db_client=db_client)
    extraction = extract_kg_from_text(
        uid,
        memory_content,
        user_name=user_name,
        existing_nodes=existing_nodes,
        db_client=db_client,
        strict_parse=strict_parse,
        usage_memory_id=memory_id,
    )
    if extraction is None:
        return None
    try:
        return _persist_extraction(uid, extraction, memory_id, existing_nodes, db_client=db_client)
    except Exception:
        logging.exception(f"Error extracting knowledge graph from memory_id: {memory_id}")
        return None


class _StagedRebuild:
    """The rebuilt graph, held in memory until every extraction has finished.

    A rebuild used to delete the stored graph first and then upsert row by row as
    each memory's LLM round-trip came back — up to 500 memories at concurrency 4,
    so a multi-minute span in which the account's only copy of its graph was a
    partial one. `BackgroundTasks` runs that driver in the serving process with no
    retry, so a deploy, restart or eviction mid-rebuild left the partial graph
    behind permanently.

    Every `get_knowledge_nodes` read that loop made saw only rows the same rebuild
    had just written (the delete had emptied the collection), so this holds that
    state instead. Resolution and merge semantics mirror `upsert_knowledge_node`
    and `upsert_knowledge_edge`, which still perform the writes at commit time.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, Dict[str, Any]] = {}
        self._label_to_node_id: Dict[str, str] = {}

    def nodes_snapshot(self) -> List[Dict[str, Any]]:
        return [dict(node) for node in self._nodes.values()]

    def nodes(self) -> List[Dict[str, Any]]:
        return list(self._nodes.values())

    def edges(self) -> List[Dict[str, Any]]:
        return list(self._edges.values())

    def apply(self, extraction: KnowledgeGraphExtraction, memory_id: str) -> None:
        for node in extraction.nodes:
            existing_id = self._label_to_node_id.get(node.label.lower())
            for alias in node.aliases:
                if not existing_id:
                    existing_id = self._label_to_node_id.get(alias.lower())
            self._apply_node(cast(str, existing_id) or str(uuid.uuid4()), node, memory_id)

        for edge in extraction.edges:
            source_id = self._label_to_node_id.get(edge.source_label.lower())
            target_id = self._label_to_node_id.get(edge.target_label.lower())
            if source_id and target_id:
                self._apply_edge(source_id, target_id, edge.label, memory_id)

    def _apply_node(self, node_id: str, node: ExtractedNode, memory_id: str) -> None:
        existing = self._nodes.get(node_id, {})
        aliases = list(set(cast(List[str], existing.get('aliases', []))) | set(node.aliases))
        memory_ids = list(set(cast(List[str], existing.get('memory_ids', []))) | {memory_id})
        self._nodes[node_id] = {
            'id': node_id,
            'label': node.label,
            'node_type': node.node_type,
            'aliases': aliases,
            'memory_ids': memory_ids,
            # `_existing_nodes_prompt_json` trims the prompt listing by recency, so
            # staged nodes carry the same field the stored rows did.
            'updated_at': datetime.now(timezone.utc),
        }
        self._label_to_node_id[node.label.lower()] = node_id
        for alias in aliases:
            self._label_to_node_id[alias.lower()] = node_id

    def _apply_edge(self, source_id: str, target_id: str, label: str, memory_id: str) -> None:
        # Same identity `upsert_knowledge_edge` derives, so repeats of one edge
        # across memories merge here exactly as they merged in Firestore.
        edge_id = f"{source_id}_{label}_{target_id}".replace('/', '_')
        existing = self._edges.get(edge_id, {})
        memory_ids = list(set(cast(List[str], existing.get('memory_ids', []))) | {memory_id})
        self._edges[edge_id] = {
            'source_id': source_id,
            'target_id': target_id,
            'label': label,
            'memory_ids': memory_ids,
        }


def rebuild_knowledge_graph(
    uid: str,
    memories: List[Dict[str, Any]],
    user_name: str = "User",
    *,
    db_client: Any = None,
) -> Dict[str, Any]:
    staged = _StagedRebuild()
    node_lock = threading.Lock()

    def process_memory(memory: Dict[str, Any]) -> None:
        memory_id = memory.get('id', str(uuid.uuid4()))
        memory_content = memory.get('content', '')
        if not memory_content:
            return

        with node_lock:
            existing_nodes_json = _existing_nodes_prompt_json(staged.nodes_snapshot())

        try:
            parser = PydanticOutputParser(pydantic_object=KnowledgeGraphExtraction)
            prompt = EXTRACTION_PROMPT.format(
                existing_nodes_json=existing_nodes_json,
                memory_content=memory_content,
                user_name=user_name,
                format_instructions=parser.get_format_instructions(),
            )

            with track_usage(uid, Features.KNOWLEDGE_GRAPH):
                response = get_llm('knowledge_graph').invoke(prompt)

            try:
                extraction: KnowledgeGraphExtraction = parser.parse(cast(str, cast(Any, response).content))
            except Exception as e:
                logger.error(f"KG extraction parse failed for memory {memory_id}: {type(e).__name__}")
                extraction = KnowledgeGraphExtraction(nodes=[], edges=[])

            with node_lock:
                staged.apply(extraction, memory_id)

        except Exception:
            logging.exception(f"Error extracting knowledge graph from memory_id: {memory_id}")

    futures: List[Any] = []
    for m in memories:
        _KG_REBUILD_SEM.acquire()
        try:
            f = llm_executor.submit(process_memory, m)
            f.add_done_callback(lambda _: _KG_REBUILD_SEM.release())
            futures.append(f)
        except Exception:
            _KG_REBUILD_SEM.release()
            raise
    for future in as_completed(futures):
        try:
            future.result()
        except Exception:
            logging.exception("Error in concurrent memory extraction")

    # Only now is the replacement graph fully known. Anything that interrupts the
    # extraction above leaves the account's stored graph untouched.
    kg_db.delete_knowledge_graph(uid, db_client=db_client)
    # `upsert_knowledge_node` resolves a node it does not find by id against label
    # and alias, so the id a node lands on is the one it returns, not necessarily
    # the one staged. Edges are written from the returned ids — the per-memory loop
    # used `saved_node['id']` for the same reason.
    landed_node_ids: Dict[str, str] = {}
    for node_data in staged.nodes():
        staged_id = node_data['id']
        saved_node = kg_db.upsert_knowledge_node(uid, node_data, db_client=db_client)
        landed_node_ids[staged_id] = saved_node['id']
    for edge_data in staged.edges():
        source_id = landed_node_ids.get(edge_data['source_id'])
        target_id = landed_node_ids.get(edge_data['target_id'])
        if not source_id or not target_id:
            continue
        kg_db.upsert_knowledge_edge(
            uid,
            {**edge_data, 'source_id': source_id, 'target_id': target_id},
            db_client=db_client,
        )

    return kg_db.get_knowledge_graph(uid, db_client=db_client)

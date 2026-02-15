from typing import List, Dict, Any, Optional
import uuid
import logging
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from .clients import llm_mini
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


def extract_knowledge_from_memory(
    uid: str, memory_content: str, memory_id: str, user_name: str = "User"
) -> Dict[str, Any]:
    existing_nodes = kg_db.get_knowledge_nodes(uid)
    existing_nodes_summary = []
    for node in existing_nodes:
        existing_nodes_summary.append(
            {
                'id': node['id'],
                'label': node['label'],
                'type': node.get('node_type', 'concept'),
                'aliases': node.get('aliases', []),
            }
        )

    existing_nodes_json = json.dumps(existing_nodes_summary) if existing_nodes_summary else "None yet"

    try:
        parser = PydanticOutputParser(pydantic_object=KnowledgeGraphExtraction)
        prompt = EXTRACTION_PROMPT.format(
            existing_nodes_json=existing_nodes_json,
            memory_content=memory_content,
            user_name=user_name,
            format_instructions=parser.get_format_instructions(),
        )

        with track_usage(uid, Features.KNOWLEDGE_GRAPH):
            response = llm_mini.invoke(prompt)
        extraction: KnowledgeGraphExtraction = parser.parse(response.content)

        label_to_node_id = {}
        for existing in existing_nodes:
            label_to_node_id[existing['label'].lower()] = existing['id']
            for alias in existing.get('aliases', []):
                label_to_node_id[alias.lower()] = existing['id']

        created_nodes = []
        for node in extraction.nodes:
            existing_id = label_to_node_id.get(node.label.lower())
            for alias in node.aliases:
                if not existing_id:
                    existing_id = label_to_node_id.get(alias.lower())

            node_id = existing_id or str(uuid.uuid4())

            node_data = {
                'id': node_id,
                'label': node.label,
                'node_type': node.node_type,
                'aliases': node.aliases,
                'memory_ids': [memory_id],
            }

            saved_node = kg_db.upsert_knowledge_node(uid, node_data)
            created_nodes.append(saved_node)
            label_to_node_id[node.label.lower()] = node_id
            for alias in node.aliases:
                label_to_node_id[alias.lower()] = node_id

        created_edges = []
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
                saved_edge = kg_db.upsert_knowledge_edge(uid, edge_data)
                created_edges.append(saved_edge)

        return {
            'nodes': created_nodes,
            'edges': created_edges,
        }

    except Exception:
        logging.exception(f"Error extracting knowledge graph from memory_id: {memory_id}")
        return {'nodes': [], 'edges': []}


def rebuild_knowledge_graph(uid: str, memories: List[Dict[str, Any]], user_name: str = "User") -> Dict[str, Any]:
    kg_db.delete_knowledge_graph(uid)

    node_lock = threading.Lock()

    def process_memory(memory):
        memory_id = memory.get('id', str(uuid.uuid4()))
        memory_content = memory.get('content', '')
        if not memory_content:
            return {'nodes': [], 'edges': []}

        existing_nodes = kg_db.get_knowledge_nodes(uid)
        existing_nodes_summary = []
        for node in existing_nodes:
            existing_nodes_summary.append(
                {
                    'id': node['id'],
                    'label': node['label'],
                    'type': node.get('node_type', 'concept'),
                    'aliases': node.get('aliases', []),
                }
            )

        existing_nodes_json = json.dumps(existing_nodes_summary) if existing_nodes_summary else "None yet"

        try:
            parser = PydanticOutputParser(pydantic_object=KnowledgeGraphExtraction)
            prompt = EXTRACTION_PROMPT.format(
                existing_nodes_json=existing_nodes_json,
                memory_content=memory_content,
                user_name=user_name,
                format_instructions=parser.get_format_instructions(),
            )

            with track_usage(uid, Features.KNOWLEDGE_GRAPH):
                response = llm_mini.invoke(prompt)
            extraction: KnowledgeGraphExtraction = parser.parse(response.content)

            created_nodes = []
            created_edges = []

            with node_lock:
                label_to_node_id = {}
                current_nodes = kg_db.get_knowledge_nodes(uid)
                for existing in current_nodes:
                    label_to_node_id[existing['label'].lower()] = existing['id']
                    for alias in existing.get('aliases', []):
                        label_to_node_id[alias.lower()] = existing['id']

                for node in extraction.nodes:
                    existing_id = label_to_node_id.get(node.label.lower())
                    for alias in node.aliases:
                        if not existing_id:
                            existing_id = label_to_node_id.get(alias.lower())

                    node_id = existing_id or str(uuid.uuid4())

                    node_data = {
                        'id': node_id,
                        'label': node.label,
                        'node_type': node.node_type,
                        'aliases': node.aliases,
                        'memory_ids': [memory_id],
                    }

                    saved_node = kg_db.upsert_knowledge_node(uid, node_data)
                    created_nodes.append(saved_node)
                    label_to_node_id[node.label.lower()] = saved_node['id']
                    for alias in node.aliases:
                        label_to_node_id[alias.lower()] = saved_node['id']

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
                        saved_edge = kg_db.upsert_knowledge_edge(uid, edge_data)
                        created_edges.append(saved_edge)

            return {'nodes': created_nodes, 'edges': created_edges}

        except Exception:
            logging.exception(f"Error extracting knowledge graph from memory_id: {memory_id}")
            return {'nodes': [], 'edges': []}

    all_nodes = []
    all_edges = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_memory, m) for m in memories]
        for future in as_completed(futures):
            try:
                result = future.result()
                all_nodes.extend(result.get('nodes', []))
                all_edges.extend(result.get('edges', []))
            except Exception:
                logging.exception("Error in concurrent memory extraction")

    return kg_db.get_knowledge_graph(uid)

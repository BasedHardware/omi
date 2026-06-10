"""
Neo4j Citation Graph Store (Optional)
Manages citation relationships between papers
"""

import logging
from typing import List, Dict, Optional
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GraphStore:
    """
    Optional Neo4j-based citation graph
    Falls back gracefully if Neo4j is unavailable
    """
    
    def __init__(self, uri: str = None, user: str = None, password: str = None, database: str = "neo4j"):
        """
        Initialize graph store
        
        Args:
            uri: Neo4j connection URI
            user: Neo4j username
            password: Neo4j password
            database: Database name
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        
        self.driver = None
        self.enabled = False
        
        if uri and user and password:
            self._connect()
    
    def _connect(self):
        """Attempt to connect to Neo4j"""
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Test connection
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            self.enabled = True
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.warning(f"Neo4j not available: {e}")
            self.enabled = False
    
    def add_paper(self, paper_id: str, title: str = None, metadata: Dict = None):
        """
        Add a paper node to the graph
        
        Args:
            paper_id: Unique paper identifier
            title: Paper title
            metadata: Additional metadata
        """
        if not self.enabled:
            return
        
        try:
            with self.driver.session(database=self.database) as session:
                query = """
                MERGE (p:Paper {id: $paper_id})
                SET p.title = $title,
                    p.metadata = $metadata
                RETURN p
                """
                session.run(query, paper_id=paper_id, title=title or paper_id, metadata=metadata or {})
        except Exception as e:
            logger.info(f"Error adding paper to graph: {e}")
    
    def add_citation(self, citing_paper_id: str, cited_paper_id: str):
        """
        Add a citation relationship
        
        Args:
            citing_paper_id: ID of the paper that cites
            cited_paper_id: ID of the paper being cited
        """
        if not self.enabled:
            return
        
        try:
            with self.driver.session(database=self.database) as session:
                query = """
                MATCH (citing:Paper {id: $citing_id})
                MATCH (cited:Paper {id: $cited_id})
                MERGE (citing)-[:CITES]->(cited)
                """
                session.run(query, citing_id=citing_paper_id, cited_id=cited_paper_id)
        except Exception as e:
            logger.info(f"Error adding citation: {e}")
    
    def get_citations(self, paper_id: str) -> Dict:
        """
        Get citation information for a paper
        
        Args:
            paper_id: Paper identifier
            
        Returns:
            Dictionary with cited_by and cites lists
        """
        if not self.enabled:
            return {'cited_by': [], 'cites': []}
        
        try:
            with self.driver.session(database=self.database) as session:
                # Papers that cite this paper
                cited_by_query = """
                MATCH (p:Paper {id: $paper_id})<-[:CITES]-(citing:Paper)
                RETURN citing.id as id, citing.title as title
                """
                cited_by = [dict(record) for record in session.run(cited_by_query, paper_id=paper_id)]
                
                # Papers cited by this paper
                cites_query = """
                MATCH (p:Paper {id: $paper_id})-[:CITES]->(cited:Paper)
                RETURN cited.id as id, cited.title as title
                """
                cites = [dict(record) for record in session.run(cites_query, paper_id=paper_id)]
                
                return {
                    'cited_by': cited_by,
                    'cites': cites
                }
        except Exception as e:
            logger.info(f"Error getting citations: {e}")
            return {'cited_by': [], 'cites': []}
    
    def delete_paper(self, paper_id: str):
        """
        Delete a paper and its citations from the graph
        
        Args:
            paper_id: Paper identifier
        """
        if not self.enabled:
            return
        
        try:
            with self.driver.session(database=self.database) as session:
                query = """
                MATCH (p:Paper {id: $paper_id})
                DETACH DELETE p
                """
                session.run(query, paper_id=paper_id)
        except Exception as e:
            logger.info(f"Error deleting paper from graph: {e}")
    
    def close(self):
        """Close the database connection"""
        if self.driver:
            self.driver.close()
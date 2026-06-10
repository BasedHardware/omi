"""
Document Parser for Club Knowledge
Parses MD, PDF, DOCX, CSV files
"""
import csv
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import re

# PDF parsing
try:
    import pypdf
except ImportError:
    pypdf = None

# DOCX parsing
try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

from utils.logger import logger


class ClubDocumentParser:
    """
    Parse various document types for club knowledge
    
    Supported formats:
    - Markdown (.md)
    - PDF (.pdf)
    - DOCX (.docx)
    - CSV (.csv)
    - Plain text (.txt)
    - JSON (.json) - for metadata
    """
    
    @staticmethod
    def parse_file(file_path: Path, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a file and return structured content
        
        Args:
            file_path: Path to file
            metadata: File metadata from Drive
            
        Returns:
            {
                "content": str,
                "metadata": dict,
                "sections": list[dict] (optional)
            }
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.md':
                return ClubDocumentParser._parse_markdown(file_path, metadata)
            elif ext == '.pdf':
                return ClubDocumentParser._parse_pdf(file_path, metadata)
            elif ext == '.docx':
                return ClubDocumentParser._parse_docx(file_path, metadata)
            elif ext == '.csv':
                return ClubDocumentParser._parse_csv(file_path, metadata)
            elif ext == '.txt':
                return ClubDocumentParser._parse_text(file_path, metadata)
            elif ext == '.json':
                return ClubDocumentParser._parse_json(file_path, metadata)
            else:
                logger.warning(f"Unsupported file type: {ext}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None
    
    @staticmethod
    def _parse_markdown(file_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Markdown file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract sections based on headers
        sections = []
        current_section = {"title": "Introduction", "content": ""}
        
        for line in content.split('\n'):
            # Check for headers (# Header)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                # Save previous section
                if current_section["content"].strip():
                    sections.append(current_section)
                
                # Start new section
                level = len(header_match.group(1))
                title = header_match.group(2)
                current_section = {
                    "title": title,
                    "level": level,
                    "content": ""
                }
            else:
                current_section["content"] += line + "\n"
        
        # Save last section
        if current_section["content"].strip():
            sections.append(current_section)
        
        return {
            "content": content,
            "metadata": metadata,
            "sections": sections
        }
    
    @staticmethod
    def _parse_pdf(file_path: Path, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse PDF file"""
        if pypdf is None:
            logger.error("pypdf not installed. Install with: pip install pypdf")
            return None
        
        try:
            reader = pypdf.PdfReader(str(file_path))
            content_parts = []
            
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text.strip():
                    content_parts.append(f"[Page {page_num}]\n{text}")
            
            content = "\n\n".join(content_parts)
            
            return {
                "content": content,
                "metadata": {
                    **metadata,
                    "num_pages": len(reader.pages)
                },
                "sections": []
            }
            
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {e}")
            return None
    
    @staticmethod
    def _parse_docx(file_path: Path, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse DOCX file"""
        if DocxDocument is None:
            logger.error("python-docx not installed. Install with: pip install python-docx")
            return None
        
        try:
            doc = DocxDocument(str(file_path))
            content_parts = []
            
            for para in doc.paragraphs:
                if para.text.strip():
                    content_parts.append(para.text)
            
            content = "\n\n".join(content_parts)
            
            return {
                "content": content,
                "metadata": metadata,
                "sections": []
            }
            
        except Exception as e:
            logger.error(f"Error parsing DOCX {file_path}: {e}")
            return None
    
    @staticmethod
    def _parse_csv(file_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse CSV file (special handling for coordinators.csv)
        
        Expected format:
        event_name,coordinator_name,role,contact
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Format as readable text
        content_lines = []
        
        # Check if this is coordinators.csv
        if 'coordinator_name' in (rows[0].keys() if rows else []):
            content_lines.append("Robotics Club Coordinators:\n")
            
            for row in rows:
                event = row.get('event_name', 'Unknown Event')
                name = row.get('coordinator_name', 'Unknown')
                role = row.get('role', 'Coordinator')
                contact = row.get('contact', 'N/A')
                
                content_lines.append(
                    f"Event: {event}\n"
                    f"Coordinator: {name}\n"
                    f"Role: {role}\n"
                    f"Contact: {contact}\n"
                )
        else:
            # Generic CSV handling
            content_lines.append("CSV Data:\n")
            for row in rows:
                line = " | ".join([f"{k}: {v}" for k, v in row.items()])
                content_lines.append(line)
        
        content = "\n".join(content_lines)
        
        return {
            "content": content,
            "metadata": {
                **metadata,
                "num_rows": len(rows),
                "columns": list(rows[0].keys()) if rows else []
            },
            "sections": [],
            "structured_data": rows  # Keep structured data for special handling
        }
    
    @staticmethod
    def _parse_text(file_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parse plain text file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "content": content,
            "metadata": metadata,
            "sections": []
        }
    
    @staticmethod
    def _parse_json(file_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JSON file (typically metadata.json)
        
        Expected format:
        {
            "event_name": "RoboSprint",
            "status": "ongoing",
            "year": 2026,
            "category": "autonomous"
        }
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Format as readable text
        content_lines = []
        for key, value in data.items():
            content_lines.append(f"{key}: {value}")
        
        content = "\n".join(content_lines)
        
        return {
            "content": content,
            "metadata": {
                **metadata,
                **data  # Merge JSON data into metadata
            },
            "sections": [],
            "structured_data": data
        }


# Singleton
parser = ClubDocumentParser()
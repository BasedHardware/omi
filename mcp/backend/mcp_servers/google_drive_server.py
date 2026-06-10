# drive_server.py
"""
Google Drive MCP Server using FastMCP
Install: pip install mcp google-auth google-auth-oauthlib google-api-python-client
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional, List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import os
from pathlib import Path

CREDS_DIR = Path(__file__).resolve().parent.parent / 'credentials'
TOKEN_PATH = CREDS_DIR / 'token.json'

# Initialize FastMCP server
mcp = FastMCP("google-drive")

# Google Drive API scopes
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata'
]

# Global Drive service instance
_drive_service = None


def get_drive_service():
    """Initialize and return Drive service (singleton pattern)"""
    global _drive_service
    
    if _drive_service is None:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(str(TOKEN_PATH), 'w') as token:
                token.write(creds.to_json())
        
        _drive_service = build('drive', 'v3', credentials=creds)
    
    return _drive_service


@mcp.tool()
def search_drive(query: str, max_results: int = 10) -> str:
    """
    Search for files in Google Drive.
    
    Args:
        query: Search query (e.g., 'name contains "report"', 'mimeType="application/pdf"')
        max_results: Maximum number of results (default: 10)
    
    Returns:
        List of matching files with details
    """
    try:
        service = get_drive_service()
        
        results = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink, owners)"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return "No files found matching your query."
        
        file_list = []
        for file in files:
            size = int(file.get('size', 0)) if file.get('size') else 0
            size_mb = size / (1024 * 1024) if size > 0 else 0
            owners = file.get('owners', [{}])
            owner_name = owners[0].get('displayName', 'Unknown') if owners else 'Unknown'
            
            file_list.append(
                f"Name: {file['name']}\n"
                f"ID: {file['id']}\n"
                f"Type: {file['mimeType']}\n"
                f"Size: {size_mb:.2f} MB\n"
                f"Owner: {owner_name}\n"
                f"Modified: {file.get('modifiedTime', 'Unknown')}\n"
                f"Link: {file.get('webViewLink', 'N/A')}\n"
            )
        
        return "\n" + "="*60 + "\n".join(file_list)
        
    except Exception as e:
        return f"❌ Error searching Drive: {str(e)}"


@mcp.tool()
def list_drive_files(folder_id: Optional[str] = None, max_results: int = 20) -> str:
    """
    List files in Google Drive or a specific folder.
    
    Args:
        folder_id: Folder ID to list files from (optional, defaults to root)
        max_results: Maximum number of results (default: 20)
    
    Returns:
        List of files with details
    """
    try:
        service = get_drive_service()
        
        query = f"'{folder_id}' in parents" if folder_id else "'root' in parents"
        query += " and trashed=false"
        
        results = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
            orderBy="modifiedTime desc"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return "No files found."
        
        file_list = []
        for file in files:
            size = int(file.get('size', 0)) if file.get('size') else 0
            size_mb = size / (1024 * 1024) if size > 0 else 0
            
            file_type = "📁 Folder" if file['mimeType'] == 'application/vnd.google-apps.folder' else "📄 File"
            
            file_list.append(
                f"{file_type}\n"
                f"Name: {file['name']}\n"
                f"ID: {file['id']}\n"
                f"Type: {file['mimeType']}\n"
                f"Size: {size_mb:.2f} MB\n"
                f"Modified: {file.get('modifiedTime', 'Unknown')}\n"
                f"Link: {file.get('webViewLink', 'N/A')}\n"
            )
        
        return "\n" + "="*60 + "\n".join(file_list)
        
    except Exception as e:
        return f"❌ Error listing files: {str(e)}"


@mcp.tool()
def get_drive_file_content(file_id: str) -> str:
    """
    Get the content of a Google Drive file (for text files and Google Docs).
    
    Args:
        file_id: The unique file ID
    
    Returns:
        File content as text
    """
    try:
        service = get_drive_service()
        
        # Get file metadata
        file_metadata = service.files().get(fileId=file_id, fields='name,mimeType').execute()
        mime_type = file_metadata['mimeType']
        
        # Handle Google Docs
        if mime_type == 'application/vnd.google-apps.document':
            content = service.files().export(
                fileId=file_id,
                mimeType='text/plain'
            ).execute()
            return f"📄 {file_metadata['name']}\n{'='*60}\n{content.decode('utf-8')}"
        
        # Handle Google Sheets
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            content = service.files().export(
                fileId=file_id,
                mimeType='text/csv'
            ).execute()
            return f"📊 {file_metadata['name']}\n{'='*60}\n{content.decode('utf-8')}"
        
        # Handle regular files
        else:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            content = fh.getvalue().decode('utf-8')
            return f"📄 {file_metadata['name']}\n{'='*60}\n{content}"
        
    except Exception as e:
        return f"❌ Error reading file: {str(e)}"


@mcp.tool()
def download_drive_file(file_id: str, destination_path: str) -> str:
    """
    Download a file from Google Drive to local storage.
    
    Args:
        file_id: The unique file ID
        destination_path: Local path where file should be saved
    
    Returns:
        Confirmation message
    """
    try:
        service = get_drive_service()
        
        # Get file metadata
        file_metadata = service.files().get(fileId=file_id, fields='name,mimeType').execute()
        
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(destination_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%")
        
        return f"✅ File '{file_metadata['name']}' downloaded to: {destination_path}"
        
    except Exception as e:
        return f"❌ Error downloading file: {str(e)}"


@mcp.tool()
def upload_drive_file(file_path: str, folder_id: Optional[str] = None, file_name: Optional[str] = None) -> str:
    """
    Upload a file to Google Drive.
    
    Args:
        file_path: Local path to the file to upload
        folder_id: Destination folder ID (optional, defaults to root)
        file_name: Name for the file in Drive (optional, uses original name)
    
    Returns:
        Upload confirmation with file details
    """
    try:
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"
        
        service = get_drive_service()
        
        name = file_name if file_name else os.path.basename(file_path)
        
        file_metadata = {'name': name}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        return (
            f"✅ File uploaded successfully!\n"
            f"Name: {file['name']}\n"
            f"ID: {file['id']}\n"
            f"Link: {file.get('webViewLink', 'N/A')}"
        )
        
    except Exception as e:
        return f"❌ Error uploading file: {str(e)}"


@mcp.tool()
def create_drive_folder(folder_name: str, parent_folder_id: Optional[str] = None) -> str:
    """
    Create a new folder in Google Drive.
    
    Args:
        folder_name: Name for the new folder
        parent_folder_id: Parent folder ID (optional, defaults to root)
    
    Returns:
        Folder creation confirmation
    """
    try:
        service = get_drive_service()
        
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        folder = service.files().create(
            body=file_metadata,
            fields='id, name, webViewLink'
        ).execute()
        
        return (
            f"✅ Folder created successfully!\n"
            f"Name: {folder['name']}\n"
            f"ID: {folder['id']}\n"
            f"Link: {folder.get('webViewLink', 'N/A')}"
        )
        
    except Exception as e:
        return f"❌ Error creating folder: {str(e)}"


@mcp.tool()
def share_drive_file(file_id: str, email: str, role: str = "reader") -> str:
    """
    Share a Google Drive file with another user.
    
    Args:
        file_id: The file ID to share
        email: Email address of the user to share with
        role: Permission role - "reader", "writer", or "commenter" (default: "reader")
    
    Returns:
        Share confirmation
    """
    try:
        service = get_drive_service()
        
        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email
        }
        
        service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()
        
        return f"✅ File shared successfully with {email} as {role}"
        
    except Exception as e:
        return f"❌ Error sharing file: {str(e)}"


@mcp.tool()
def delete_drive_file(file_id: str) -> str:
    """
    Delete a file from Google Drive (moves to trash).
    
    Args:
        file_id: The file ID to delete
    
    Returns:
        Deletion confirmation
    """
    try:
        service = get_drive_service()
        
        # Get file name before deleting
        file = service.files().get(fileId=file_id, fields='name').execute()
        
        service.files().delete(fileId=file_id).execute()
        
        return f"✅ File '{file['name']}' moved to trash"
        
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"


@mcp.tool()
def get_drive_file_metadata(file_id: str) -> str:
    """
    Get detailed metadata for a Google Drive file.
    
    Args:
        file_id: The file ID
    
    Returns:
        Complete file metadata
    """
    try:
        service = get_drive_service()
        
        file = service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, size, createdTime, modifiedTime, owners, permissions, webViewLink, description'
        ).execute()
        
        size = int(file.get('size', 0)) if file.get('size') else 0
        size_mb = size / (1024 * 1024) if size > 0 else 0
        
        owners = file.get('owners', [{}])
        owner_info = ', '.join([o.get('displayName', 'Unknown') for o in owners])
        
        return (
            f"📄 File Metadata\n"
            f"{'='*60}\n"
            f"Name: {file['name']}\n"
            f"ID: {file['id']}\n"
            f"Type: {file['mimeType']}\n"
            f"Size: {size_mb:.2f} MB\n"
            f"Created: {file.get('createdTime', 'Unknown')}\n"
            f"Modified: {file.get('modifiedTime', 'Unknown')}\n"
            f"Owner(s): {owner_info}\n"
            f"Description: {file.get('description', 'None')}\n"
            f"Link: {file.get('webViewLink', 'N/A')}\n"
        )
        
    except Exception as e:
        return f"❌ Error getting metadata: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
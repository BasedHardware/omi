# test_club_drive.py
from knowledge_engine.club.drive_client import drive_client

try:
    print("✓ Service account authenticated successfully!")
    print(f"✓ Connected to folder ID: {drive_client.root_folder_id}")
    
    # Try listing top-level folders
    results = drive_client.service.files().list(
        q=f"'{drive_client.root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    
    folders = results.get('files', [])
    print(f"\n✓ Found {len(folders)} folders:")
    for folder in folders:
        print(f"  - {folder['name']}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    print("\nTroubleshooting:")
    print("1. Check service account JSON exists at: backend/credentials/club_service_account.json")
    print("2. Verify CLUB_DRIVE_FOLDER_ID in .env")
    print("3. Ensure folder is shared with service account email")
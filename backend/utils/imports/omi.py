import io
import json
import os
import uuid
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any
from zipfile import ZipFile

import database.import_jobs as import_jobs_db
import database.conversations as conversations_db
import database.memories as memories_db
import database.chat as chat_db
from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
from utils.notifications import send_notification


def get_all_memories(uid: str) -> List[Dict[str, Any]]:
    all_memories = []
    offset = 0
    batch_size = 500
    
    while True:
        batch = memories_db.get_non_filtered_memories(uid, limit=batch_size, offset=offset)
        if not batch:
            break
        all_memories.extend(batch)
        offset += batch_size
        if len(batch) < batch_size:
            break
    
    return all_memories


def get_all_conversations(uid: str) -> List[Dict[str, Any]]:
    all_conversations = []
    offset = 0
    batch_size = 500
    
    while True:
        batch = conversations_db.get_conversations(uid, limit=batch_size, offset=offset, include_discarded=True)
        if not batch:
            break
        all_conversations.extend(batch)
        offset += batch_size
        if len(batch) < batch_size:
            break
    
    return all_conversations


def get_all_chat_messages(uid: str) -> List[Dict[str, Any]]:
    all_messages = []
    offset = 0
    batch_size = 500
    
    while True:
        batch = chat_db.get_messages(uid, limit=batch_size, offset=offset)
        if not batch:
            break
        all_messages.extend(batch)
        offset += batch_size
        if len(batch) < batch_size:
            break
    
    return all_messages


def serialize_for_json(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    return obj


def export_omi_data(uid: str) -> io.BytesIO:
    memories = get_all_memories(uid)
    conversations = get_all_conversations(uid)
    chat_messages = get_all_chat_messages(uid)
    
    memories = serialize_for_json(memories)
    conversations = serialize_for_json(conversations)
    chat_messages = serialize_for_json(chat_messages)
    
    zip_buffer = io.BytesIO()
    date_str = datetime.now().strftime('%Y-%m-%d')
    folder_name = f'omi_export_{date_str}'
    
    with ZipFile(zip_buffer, 'w') as zf:
        zf.writestr(
            f'{folder_name}/memories.json',
            json.dumps(memories, indent=2, ensure_ascii=False)
        )
        zf.writestr(
            f'{folder_name}/conversations.json',
            json.dumps(conversations, indent=2, ensure_ascii=False)
        )
        zf.writestr(
            f'{folder_name}/chat_history.json',
            json.dumps(chat_messages, indent=2, ensure_ascii=False)
        )
    
    zip_buffer.seek(0)
    return zip_buffer


def create_import_job(uid: str, source_type: ImportSourceType = ImportSourceType.omi) -> ImportJob:
    job = ImportJob(
        id=str(uuid.uuid4()),
        uid=uid,
        status=ImportJobStatus.pending,
        source_type=source_type,
    )
    import_jobs_db.create_import_job(job.dict())
    return job


def process_omi_import(job_id: str, uid: str, zip_path: str) -> None:
    try:
        import_jobs_db.update_import_job(
            job_id,
            {
                'status': ImportJobStatus.processing.value,
                'started_at': datetime.now(timezone.utc).isoformat(),
            },
        )
        
        with ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()
            
            memories_file = None
            conversations_file = None
            chat_file = None
            
            for name in all_files:
                if name.endswith('memories.json'):
                    memories_file = name
                elif name.endswith('conversations.json'):
                    conversations_file = name
                elif name.endswith('chat_history.json'):
                    chat_file = name
            
            total_items = 0
            processed_items = 0
            memories_imported = 0
            conversations_imported = 0
            messages_imported = 0
            
            if memories_file:
                with zf.open(memories_file) as f:
                    memories = json.load(f)
                total_items += len(memories)
            else:
                memories = []
            
            if conversations_file:
                content = zf.read(conversations_file).decode('utf-8')
                conversations = json.loads(content)
                total_items += len(conversations)
            else:
                conversations = []
            
            if chat_file:
                content = zf.read(chat_file).decode('utf-8')
                chat_messages = json.loads(content)
                total_items += len(chat_messages)
            else:
                chat_messages = []
            
            import_jobs_db.update_import_job(job_id, {'total_files': total_items})
            
            if total_items == 0:
                import_jobs_db.update_import_job(
                    job_id,
                    {
                        'status': ImportJobStatus.failed.value,
                        'error': 'No data found in ZIP file',
                        'completed_at': datetime.now(timezone.utc).isoformat(),
                    },
                )
                return
            
            for memory in memories:
                try:
                    memory['source'] = 'omi_imported'
                    memories_db.create_memory(uid, memory)
                    memories_imported += 1
                except Exception as e:
                    print(f"Error importing memory: {e}")
                
                processed_items += 1
                if processed_items % 50 == 0:
                    import_jobs_db.update_import_job(job_id, {'processed_files': processed_items})
            
            for conversation in conversations:
                try:
                    conversation['source'] = 'omi_imported'
                    conversations_db.upsert_conversation(uid, conversation)
                    conversations_imported += 1
                except Exception as e:
                    print(f"Error importing conversation: {e}")
                
                processed_items += 1
                if processed_items % 50 == 0:
                    import_jobs_db.update_import_job(job_id, {'processed_files': processed_items})
            
            for message in chat_messages:
                try:
                    message.update({'memories': [], 'source': 'omi_imported'})
                    chat_db.add_message(uid, message)
                    messages_imported += 1
                except Exception as e:
                    print(f"Error importing message: {e}")
                
                processed_items += 1
                if processed_items % 50 == 0:
                    import_jobs_db.update_import_job(job_id, {'processed_files': processed_items})
            
            import_jobs_db.update_import_job(
                job_id,
                {
                    'status': ImportJobStatus.completed.value,
                    'processed_files': processed_items,
                    'conversations_created': conversations_imported,
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                },
            )
            
            send_notification(
                user_id=uid,
                title="OMI Import Complete! 🎉",
                body=f"Imported {memories_imported} memories, {conversations_imported} conversations, {messages_imported} messages.",
                data={
                    'type': 'import_complete',
                    'job_id': job_id,
                },
            )
    
    except Exception as e:
        print(f"Import job {job_id} failed: {str(e)}")
        traceback.print_exc()
        import_jobs_db.update_import_job(
            job_id,
            {
                'status': ImportJobStatus.failed.value,
                'error': str(e),
                'completed_at': datetime.now(timezone.utc).isoformat(),
            },
        )
        
        send_notification(
            user_id=uid,
            title="OMI Import Failed",
            body="There was an error importing your data. Please try again.",
            data={'type': 'import_failed', 'job_id': job_id},
        )
    
    finally:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            print(f"Failed to clean up ZIP file {zip_path}: {e}")

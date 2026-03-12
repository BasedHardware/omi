"""
Limitless data import utilities.

Parses Limitless lifelog exports and creates Omi conversations.
Uses "light import" mode - no AI processing, just stores the data directly.
"""

import os
import re
import uuid
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional
from zipfile import ZipFile

import database.import_jobs as import_jobs_db
import database.conversations as conversations_db
from models.conversation import (
    Conversation,
    ConversationSource,
    ConversationStatus,
    Structured,
    CategoryEnum,
    AppResult,
)
from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
from models.transcript_segment import TranscriptSegment
from utils.notifications import send_notification
import logging

logger = logging.getLogger(__name__)


def parse_lifelog_filename(filename: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Extract datetime and title slug from a Limitless lifelog filename.

    Filename format: 2025-10-08_07h00m25s_Title-slug-here.md

    Returns:
        Tuple of (started_at datetime, title_slug) or (None, None) if parsing fails
    """
    basename = Path(filename).stem  # Remove .md extension

    # Pattern: YYYY-MM-DD_HHhMMmSSs_title-slug
    match = re.match(r'(\d{4}-\d{2}-\d{2})_(\d{2})h(\d{2})m(\d{2})s_(.+)', basename)
    if not match:
        return None, None

    date_str, hour, minute, second, title_slug = match.groups()

    try:
        started_at = datetime.strptime(f"{date_str} {hour}:{minute}:{second}", "%Y-%m-%d %H:%M:%S")
        started_at = started_at.replace(tzinfo=timezone.utc)
    except ValueError:
        return None, None

    return started_at, title_slug


def parse_lifelog_md(
    content: str, filename: str
) -> Tuple[Optional[datetime], List[TranscriptSegment], Optional[str], Optional[str], Optional[str]]:
    """
    Parse a Limitless lifelog markdown file into transcript segments.

    Args:
        content: The markdown file content
        filename: The filename (used to extract started_at timestamp)

    Returns:
        Tuple of (started_at, list of TranscriptSegment, title, plain_summary, formatted_summary)
        - plain_summary: unformatted text dump of H2/H3 headers (for overview)
        - formatted_summary: markdown formatted H2 headers + H3 as bullet points (for apps_results)
    """
    started_at, title_slug = parse_lifelog_filename(filename)

    # Extract title from first H1 header
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = (
        title_match.group(1).strip()
        if title_match
        else title_slug.replace('-', ' ') if title_slug else 'Imported Conversation'
    )

    # Extract H2 and H3 headers (these are Limitless AI-generated topic summaries)
    # Create two versions:
    # 1. formatted_summary: H2 as markdown headers, H3 as bullet points (for apps_results)
    #    - If all headers are H2 (no H3s), convert H2s to bullet points instead
    # 2. plain_summary: unformatted text dump (for overview)
    plain_parts = []
    header_data = []  # List of (hashes, text) tuples

    # First pass: collect all headers and check for H3s
    has_h3 = False
    for match in re.finditer(r'^(#{2,3})\s+(.+)$', content, re.MULTILINE):
        hashes, text = match.groups()
        text = text.strip()
        plain_parts.append(text)
        header_data.append((hashes, text))
        if hashes == '###':
            has_h3 = True

    # Second pass: format based on whether H3s exist
    formatted_parts = []
    for hashes, text in header_data:
        if hashes == '##':
            if has_h3:
                # Keep H2 as markdown header when H3s are present
                formatted_parts.append(f'## {text}')
            else:
                # Convert H2 to bullet point when no H3s exist
                formatted_parts.append(f'- {text}')
        else:
            # Convert H3 to markdown bullet point
            formatted_parts.append(f'- {text}')

    formatted_summary = '\n\n'.join(formatted_parts) if formatted_parts else None
    plain_summary = '\n'.join(plain_parts) if plain_parts else None

    # Parse quotes: > [SpeakerID](#startMs=xxx&endMs=yyy): Text
    # The format is: > [N](#startMs=TIMESTAMP&endMs=TIMESTAMP): TEXT
    quote_pattern = r'>\s*\[(\d+)\]\(#startMs=(\d+)&endMs=(\d+)\):\s*(.+)'

    segments: List[TranscriptSegment] = []
    min_timestamp_ms = None

    for match in re.finditer(quote_pattern, content):
        speaker_id_str, start_ms_str, end_ms_str, text = match.groups()

        speaker_id = int(speaker_id_str)
        start_ms = int(start_ms_str)
        end_ms = int(end_ms_str)

        # Track minimum timestamp to calculate relative times
        if min_timestamp_ms is None or start_ms < min_timestamp_ms:
            min_timestamp_ms = start_ms

        segments.append(
            {
                'speaker_id': speaker_id,
                'start_ms': start_ms,
                'end_ms': end_ms,
                'text': text.strip(),
            }
        )

    # Convert to TranscriptSegment objects with relative timestamps in seconds
    transcript_segments: List[TranscriptSegment] = []

    for seg in segments:
        # Calculate relative time from start of conversation (in seconds)
        if min_timestamp_ms:
            start_seconds = (seg['start_ms'] - min_timestamp_ms) / 1000.0
            end_seconds = (seg['end_ms'] - min_timestamp_ms) / 1000.0
        else:
            start_seconds = 0.0
            end_seconds = 0.0

        # Speaker 1 is typically the user in Limitless
        is_user = seg['speaker_id'] == 1

        transcript_segment = TranscriptSegment(
            text=seg['text'],
            speaker=f"SPEAKER_{seg['speaker_id']:02d}",
            speaker_id=seg['speaker_id'],
            is_user=is_user,
            start=start_seconds,
            end=end_seconds,
        )
        transcript_segments.append(transcript_segment)

    # If we found timestamps in the content, use the first one as started_at
    if min_timestamp_ms and not started_at:
        started_at = datetime.fromtimestamp(min_timestamp_ms / 1000.0, tz=timezone.utc)

    return started_at, transcript_segments, title, plain_summary, formatted_summary


def _create_overview_from_transcript(segments: List[TranscriptSegment], max_chars: int = 500) -> str:
    """
    Fallback: Create a simple overview from transcript segments.
    Takes the first few segments up to max_chars.
    Only used if no H2/H3 headers are found.
    """
    if not segments:
        return "Imported from Limitless"

    texts = []
    total_chars = 0

    for seg in segments:
        if total_chars + len(seg.text) > max_chars:
            break
        texts.append(seg.text)
        total_chars += len(seg.text) + 1  # +1 for space

    overview = ' '.join(texts)
    if len(overview) > max_chars:
        overview = overview[: max_chars - 3] + '...'

    return overview if overview else "Imported from Limitless"


def process_limitless_import(job_id: str, uid: str, zip_path: str, language_code: str = 'en') -> None:
    """
    Background worker to process a Limitless ZIP export using LIGHT IMPORT mode.

    Light import mode:
    - Uses the title directly from the Limitless markdown
    - Creates a simple overview from the transcript (no AI)
    - Skips AI processing (no memories, trends, action items, apps)
    - Just stores the conversation with transcript

    This makes imports almost instant (~0.1 sec per file instead of ~7 sec).

    Args:
        job_id: The import job ID
        uid: User ID
        zip_path: Path to the uploaded ZIP file
        language_code: Language code for conversation processing
    """
    try:
        # Update status to processing
        import_jobs_db.update_import_job(
            job_id,
            {
                'status': ImportJobStatus.processing.value,
                'started_at': datetime.now(timezone.utc).isoformat(),
            },
        )

        # Open and scan the ZIP file
        with ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()
            logger.info(f"[Limitless Import] ZIP contains {len(all_files)} entries")
            logger.info(f"[Limitless Import] First 20 entries: {all_files[:20]}")

            # Find all lifelog markdown files
            # Handle both "lifelogs/..." and "something/lifelogs/..." structures
            lifelog_files = [
                name
                for name in all_files
                if ('lifelogs/' in name or name.startswith('lifelogs')) and name.endswith('.md')
            ]

            logger.info(f"[Limitless Import] Found {len(lifelog_files)} lifelog files")
            if lifelog_files:
                logger.info(f"[Limitless Import] First 5 lifelog files: {lifelog_files[:5]}")

            total_files = len(lifelog_files)
            import_jobs_db.update_import_job(job_id, {'total_files': total_files})

            if total_files == 0:
                # Log more details about what we found
                md_files = [name for name in all_files if name.endswith('.md')]
                logger.info(f"[Limitless Import] Total .md files found: {len(md_files)}")
                if md_files:
                    logger.info(f"[Limitless Import] Sample .md files: {md_files[:10]}")

                import_jobs_db.update_import_job(
                    job_id,
                    {
                        'status': ImportJobStatus.failed.value,
                        'error': f'No lifelog files found in ZIP. Found {len(all_files)} total entries, {len(md_files)} .md files. Expected files in lifelogs/ folder.',
                        'completed_at': datetime.now(timezone.utc).isoformat(),
                    },
                )
                return

            processed_files = 0
            conversations_created = 0
            errors = []

            for lifelog_path in lifelog_files:
                try:
                    # Read and parse the lifelog
                    content = zf.read(lifelog_path).decode('utf-8')
                    filename = Path(lifelog_path).name

                    started_at, segments, title, plain_summary, formatted_summary = parse_lifelog_md(content, filename)

                    # Skip empty files
                    if not segments:
                        processed_files += 1
                        import_jobs_db.update_import_job(job_id, {'processed_files': processed_files})
                        continue

                    # Calculate finished_at from last segment
                    if segments and started_at:
                        last_segment_end = max(seg.end for seg in segments)
                        finished_at = datetime.fromtimestamp(started_at.timestamp() + last_segment_end, tz=timezone.utc)
                    else:
                        finished_at = started_at or datetime.now(timezone.utc)

                    if not started_at:
                        started_at = datetime.now(timezone.utc)

                    # Use plain summary (unformatted H2/H3 headers) for overview,
                    # fall back to transcript excerpt if no headers found
                    overview = plain_summary if plain_summary else _create_overview_from_transcript(segments)

                    # Create apps_results with formatted markdown summary
                    apps_results = []
                    if formatted_summary:
                        apps_results.append(AppResult(app_id='01KBTYQAZSQFRZ809BQ46HW76M', content=formatted_summary))

                    # Create structured data directly (no AI)
                    structured = Structured(
                        title=title or 'Imported Conversation',
                        overview=overview,
                        emoji='💬',
                        category=CategoryEnum.other,
                        action_items=[],
                        events=[],
                    )

                    # Create conversation object directly
                    conversation = Conversation(
                        id=str(uuid.uuid4()),
                        created_at=started_at,  # Use started_at as created_at for proper ordering
                        started_at=started_at,
                        finished_at=finished_at,
                        source=ConversationSource.limitless,
                        language=language_code,
                        structured=structured,
                        transcript_segments=segments,
                        apps_results=apps_results,
                        status=ConversationStatus.completed,
                        discarded=False,
                    )

                    # Save directly to database (skip all AI processing)
                    conversations_db.upsert_conversation(uid, conversation.dict())
                    conversations_created += 1

                except Exception as e:
                    error_msg = f"Error processing {lifelog_path}: {str(e)}"
                    logger.info(error_msg)
                    errors.append(error_msg)

                processed_files += 1

                # Update progress every 10 files to reduce database writes
                if processed_files % 10 == 0 or processed_files == total_files:
                    import_jobs_db.update_import_job(
                        job_id,
                        {
                            'processed_files': processed_files,
                            'conversations_created': conversations_created,
                        },
                    )

            # Mark as completed
            final_status = ImportJobStatus.completed.value
            error_msg = None

            if errors:
                if conversations_created == 0:
                    final_status = ImportJobStatus.failed.value
                    error_msg = f"All files failed to process. First error: {errors[0]}"
                else:
                    # Partial success
                    error_msg = f"{len(errors)} files failed to process"

            import_jobs_db.update_import_job(
                job_id,
                {
                    'status': final_status,
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                    'error': error_msg,
                },
            )

            # Send push notification
            if final_status == ImportJobStatus.completed.value:
                send_notification(
                    user_id=uid,
                    title="Limitless Import Complete! 🎉",
                    body=f"Successfully imported {conversations_created} conversations from your Limitless data.",
                    data={
                        'type': 'import_complete',
                        'job_id': job_id,
                        'conversations_created': str(conversations_created),
                    },
                )
            else:
                send_notification(
                    user_id=uid,
                    title="Limitless Import Failed",
                    body=error_msg or "There was an error importing your data. Please try again.",
                    data={'type': 'import_failed', 'job_id': job_id},
                )

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {str(e)}")
        traceback.print_exc()
        import_jobs_db.update_import_job(
            job_id,
            {
                'status': ImportJobStatus.failed.value,
                'error': str(e),
                'completed_at': datetime.now(timezone.utc).isoformat(),
            },
        )

        # Send failure notification
        send_notification(
            user_id=uid,
            title="Limitless Import Failed",
            body="There was an error importing your data. Please try again.",
            data={'type': 'import_failed', 'job_id': job_id},
        )

    finally:
        # Clean up the ZIP file
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            logger.error(f"Failed to clean up ZIP file {zip_path}: {e}")


def create_import_job(uid: str, source_type: ImportSourceType = ImportSourceType.limitless) -> ImportJob:
    """Create a new import job record."""
    job = ImportJob(
        id=str(uuid.uuid4()),
        uid=uid,
        status=ImportJobStatus.pending,
        source_type=source_type,
    )
    import_jobs_db.create_import_job(job.dict())
    return job

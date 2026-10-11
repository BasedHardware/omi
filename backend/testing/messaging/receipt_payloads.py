"""Deterministic real serializer fixtures shared with mobile receipt tests."""

from datetime import datetime, timezone

from models.chat import EditReceiptBlock, Message, MessageSender, MessageType, UndoChatReceiptResponse
from utils.messaging.receipt_presentation import app_receipt_text
from utils.messaging.undo import edit_receipt_block


def receipt_payloads():
    scenarios = [
        (
            'task',
            {'_snapshot': {'completed': False}, '_summary': 'Task'},
            {'_snapshot': {'completed': True}, '_summary': 'Book flights to Lisbon'},
        ),
        (
            'task',
            {'_snapshot': {'description': 'Old'}, '_summary': 'Task'},
            {'_snapshot': {'description': 'Send the Q4 deck to Priya'}, '_summary': 'Send the Q4 deck to Priya'},
        ),
        (
            'memory_deleted',
            {'content': 'Prefers window seats'},
            {'content': 'Prefers window seats', 'promotion': {'chat_deleted': True}},
        ),
        (
            'conversation',
            {'_snapshot': {'structured': {'title': 'Old'}}, '_summary': 'Conversation'},
            {'_snapshot': {'structured': {'title': 'Pricing sync'}}, '_summary': 'Title → Pricing sync'},
        ),
        (
            'person',
            {'_snapshot': {'name': 'Speaker 2'}, '_summary': 'Person'},
            {'_snapshot': {'name': 'Priya'}, '_summary': 'Name → Priya'},
        ),
        ('memory_edit', {'content': 'Old fact'}, {'content': 'Confirmed fact'}),
    ]
    blocks, messages, undo_responses = [], [], {}
    at = datetime(2026, 10, 11, 10, tzinfo=timezone.utc)
    for index, (kind, before, after) in enumerate(scenarios, start=1):
        receipt_id = f'{index:032x}'
        block = EditReceiptBlock.model_validate(
            edit_receipt_block(receipt_id, kind, 'item-' + str(index), before, after)
        )
        if index == 3:
            block = EditReceiptBlock.model_validate({**block.model_dump(), 'undoable': False, 'undoneAt': at})
        if index == 6:
            block = EditReceiptBlock.model_validate({**block.model_dump(), 'undoable': False})
        payload = block.model_dump(mode='json')
        blocks.append(payload)
        message = Message(
            id='message-' + str(index),
            sender=MessageSender.ai,
            type=MessageType.text,
            created_at=at,
            text=app_receipt_text('Done.', [payload]),
            content_blocks=[payload],
        )
        messages.append(message.model_dump(mode='json'))
        undone = EditReceiptBlock.model_validate({**block.model_dump(), 'undoable': False, 'undoneAt': at})
        undo_responses[receipt_id] = UndoChatReceiptResponse(status='undone', block=undone).model_dump(mode='json')
    return {'blocks': blocks, 'messages': messages, 'undo_responses': undo_responses}

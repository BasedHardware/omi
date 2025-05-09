#!/usr/bin/env python3

import argparse
import sys
import os

# Add parent directory to path so Python can find our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database.memories as memories_db

def list_memories(uid, limit=10, offset=0):
    """List memories for a user"""
    print(f"Listing memories for user {uid} (limit: {limit}, offset: {offset})")

    try:
        memories = memories_db.get_non_filtered_memories(uid, limit, offset)

        if not memories:
            print("No memories found")
            return []

        print(f"Found {len(memories)} memories:")
        for i, memory in enumerate(memories):
            visibility = memory.get('visibility', 'public')
            print(f"{i+1}. ID: {memory['id']}")
            print(f"   Content: {memory['content']}")
            print(f"   Category: {memory['category']}")
            print(f"   Visibility: {visibility}")
            print(f"   Created: {memory['created_at']}")
            print(f"   Reviewed: {memory['reviewed']} (User Review: {memory['user_review']})")
            print()

        return memories
    except Exception as e:
        print(f"Error listing memories: {e}")
        return []

def review_memory(uid, memory_id, approve=True):
    """Review a memory (approve or reject)"""
    try:
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            print(f"Memory with ID {memory_id} not found")
            return False

        print(f"Reviewing memory: {memory['content']}")
        print(f"Setting review to: {'Approved' if approve else 'Rejected'}")

        memories_db.review_memory(uid, memory_id, approve)
        print("Memory review status updated successfully")
        return True
    except Exception as e:
        print(f"Error reviewing memory: {e}")
        return False

def delete_memory(uid, memory_id):
    """Delete a single memory"""
    try:
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            print(f"Memory with ID {memory_id} not found")
            return False

        print(f"Deleting memory: {memory['content']}")

        memories_db.delete_memory(uid, memory_id)
        print("Memory marked as deleted successfully")
        return True
    except Exception as e:
        print(f"Error deleting memory: {e}")
        return False

def edit_memory(uid, memory_id, new_content):
    """Edit a memory's content"""
    try:
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            print(f"Memory with ID {memory_id} not found")
            return False

        print(f"Editing memory:")
        print(f"Old content: {memory['content']}")
        print(f"New content: {new_content}")

        memories_db.edit_memory(uid, memory_id, new_content)
        print("Memory content updated successfully")
        return True
    except Exception as e:
        print(f"Error editing memory: {e}")
        return False

def change_visibility(uid, memory_id, visibility):
    """Change memory visibility (public/private)"""
    if visibility not in ['public', 'private']:
        print(f"Invalid visibility: {visibility}. Must be 'public' or 'private'")
        return False

    try:
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            print(f"Memory with ID {memory_id} not found")
            return False

        print(f"Changing visibility for memory: {memory['content']}")
        print(f"Old visibility: {memory.get('visibility', 'public')}")
        print(f"New visibility: {visibility}")

        memories_db.change_memory_visibility(uid, memory_id, visibility)
        print("Memory visibility updated successfully")
        return True
    except Exception as e:
        print(f"Error changing memory visibility: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test tools for managing memories')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List memories command
    list_parser = subparsers.add_parser('list', help='List memories')
    list_parser.add_argument('--uid', type=str, required=True, help='User ID')
    list_parser.add_argument('--limit', type=int, default=10, help='Number of memories to list (default: 10)')
    list_parser.add_argument('--offset', type=int, default=0, help='Offset for listing memories (default: 0)')

    # Review memory command
    review_parser = subparsers.add_parser('review', help='Review a memory')
    review_parser.add_argument('--uid', type=str, required=True, help='User ID')
    review_parser.add_argument('--memory-id', type=str, required=True, help='Memory ID')
    review_parser.add_argument('--approve', action='store_true', help='Approve the memory (default)')
    review_parser.add_argument('--reject', action='store_false', dest='approve', help='Reject the memory')

    # Delete memory command
    delete_parser = subparsers.add_parser('delete', help='Delete a memory')
    delete_parser.add_argument('--uid', type=str, required=True, help='User ID')
    delete_parser.add_argument('--memory-id', type=str, required=True, help='Memory ID')

    # Edit memory command
    edit_parser = subparsers.add_parser('edit', help='Edit a memory')
    edit_parser.add_argument('--uid', type=str, required=True, help='User ID')
    edit_parser.add_argument('--memory-id', type=str, required=True, help='Memory ID')
    edit_parser.add_argument('--content', type=str, required=True, help='New memory content')

    # Change visibility command
    visibility_parser = subparsers.add_parser('visibility', help='Change memory visibility')
    visibility_parser.add_argument('--uid', type=str, required=True, help='User ID')
    visibility_parser.add_argument('--memory-id', type=str, required=True, help='Memory ID')
    visibility_parser.add_argument('--visibility', type=str, required=True, choices=['public', 'private'],
                               help='New visibility setting (public/private)')

    args = parser.parse_args()

    if args.command == 'list':
        list_memories(args.uid, args.limit, args.offset)
    elif args.command == 'review':
        review_memory(args.uid, args.memory_id, args.approve)
    elif args.command == 'delete':
        delete_memory(args.uid, args.memory_id)
    elif args.command == 'edit':
        edit_memory(args.uid, args.memory_id, args.content)
    elif args.command == 'visibility':
        change_visibility(args.uid, args.memory_id, args.visibility)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
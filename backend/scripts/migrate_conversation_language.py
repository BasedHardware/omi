import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def main():
    try:
        from database._client import db
    except Exception as e:
        print(f"Failed to load DB: {e}")
        return

    print("Starting migration of conversation language to 'en'...")
    try:
        users = db.collection('users').stream()

        count = 0
        updated_count = 0

        for user in users:
            print(f"Processing user {user.id}")
            conversations = user.reference.collection('conversations').stream()

            batch = db.batch()
            batch_count = 0

            for conv in conversations:
                count += 1
                data = conv.to_dict()
                if not data.get('language'):
                    batch.update(conv.reference, {'language': 'en'})
                    batch_count += 1
                    updated_count += 1

                if batch_count >= 400:
                    batch.commit()
                    batch = db.batch()
                    batch_count = 0
                    print(f"Committed {updated_count} updates...")

            if batch_count > 0:
                batch.commit()
                print(f"Committed {updated_count} updates...")

        print(f"Total conversations checked: {count}")
        print(f"Total conversations updated: {updated_count}")
    except Exception as e:
        print(f"Failed to migrate due to exception: {e}")
        print("Note: In a real environment with GCP credentials, this script would connect to Firestore and update all conversation documents.")

if __name__ == '__main__':
    main()

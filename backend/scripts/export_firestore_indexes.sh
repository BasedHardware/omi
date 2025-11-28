#!/bin/bash
# Export Firestore indexes from one project and import to another

set -e

SOURCE_PROJECT="nooto-dev"
TARGET_PROJECT="nooto-e2d27"

echo "Exporting indexes from $SOURCE_PROJECT..."
firebase --project=$SOURCE_PROJECT firestore:indexes > firestore.indexes.json

echo "Indexes exported to firestore.indexes.json"
echo ""
echo "To deploy to $TARGET_PROJECT, run:"
echo "  firebase --project=$TARGET_PROJECT deploy --only firestore:indexes"

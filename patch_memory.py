import re

with open('app/lib/backend/schema/memory_review.dart', 'r') as f:
    content = f.read()

content = content.replace("memoryId: generated.memoryId", "memoryId: generated.id")

with open('app/lib/backend/schema/memory_review.dart', 'w') as f:
    f.write(content)

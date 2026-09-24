with open('app/lib/backend/schema/memory_review.dart', 'r') as f:
    content = f.read()

content = content.replace("memoryId: generated.memoryId", "memoryId: generated.id")

with open('app/lib/backend/schema/memory_review.dart', 'w') as f:
    f.write(content)

with open('app/lib/backend/schema/memory.dart', 'r') as f:
    content = f.read()

content = content.replace("      'memory_id': conversationId,\n", "")

with open('app/lib/backend/schema/memory.dart', 'w') as f:
    f.write(content)

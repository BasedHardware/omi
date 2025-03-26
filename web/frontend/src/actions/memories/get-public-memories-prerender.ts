import { Memory } from '@/src/types/memory.types';
import getPublicMemories from './get-public-memories';

export default async function getPublicMemoriesPrerender(maxCount = 40000) {
  const limit = 500;
  const totalRequests = Math.ceil(maxCount / limit);
  const concurrentRequests = 10;
  let memories: Memory[] = [];

  for (let i = 0; i < totalRequests; i += concurrentRequests) {
    const promises = [];
    for (let j = 0; j < concurrentRequests && i + j < totalRequests; j++) {
      const offset = (i + j) * limit;
      promises.push(getPublicMemories(offset, limit));
    }
    const results = await Promise.all(promises);
    memories = memories.concat(results.flat());
  }

  return memories;
}

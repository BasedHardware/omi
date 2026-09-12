'use server';
import envConfig from '@/src/constants/envConfig';
import { Memory } from '@/src/types/memory.types';
import { sharedApiUrl } from '@/src/lib/shared-api-url.mjs';

export default async function getSharedMemory(id: string) {
  try {
    const response = await fetch(
      sharedApiUrl(envConfig.API_URL, 'v1', 'conversations', id, 'shared'),
      {
        headers: {
          'Content-Type': 'application/json',
        },
        cache: 'no-cache',
      },
    );
    if (!response.ok) {
      return undefined;
    }
    return (await response.json()) as Memory;
  } catch (err) {
    return undefined;
  }
}

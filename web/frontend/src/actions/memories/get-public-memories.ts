'use server';

import envConfig from '@/src/constants/envConfig';
import { Memory } from '@/src/types/memory.types';

export default async function getPublicMemories(
  offset = 0,
  limit = 20,
): Promise<Memory[]> {
  try {
    const response = await fetch(
      `${envConfig.API_URL}/v1/public-memories?offset=${offset}&limit=${limit}`,
      {
        headers: {
          'Content-Type': 'application/json',
        },
        next: { revalidate: 60 * 60 },
      },
    );
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as Memory[];
  } catch (err) {
    return [];
  }
}

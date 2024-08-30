'use server';

import envConfig from '@/src/constants/envConfig';
import { Memory } from '@/src/types/memory.types';

export default async function getPublicMemories() {
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/public-memories/`, {
      headers: {
        'Content-Type': 'application/json',
      },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as Memory[];
  } catch (err) {
    return [];
  }
}

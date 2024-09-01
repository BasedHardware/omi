'use server';
import envConfig from '@/src/constants/envConfig';
import { Memory } from '@/src/types/memory.types';

// example: 32190a0f-8229-4189-93a9-ba8156c952cb

export default async function getSharedMemory(id: string) {
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/memories/${id}/shared`, {
      headers: {
        'Content-Type': 'application/json',
      },
      next: { revalidate: 86400 },
    });
    if (!response.ok) {
      return undefined;
    }
    return (await response.json()) as Memory;
  } catch (err) {
    return undefined;
  }
}

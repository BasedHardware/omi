'use server';
import envConfig from '@/src/constants/envConfig';

export interface SharedTaskData {
  sender_name: string;
  tasks: { description: string; due_at: string | null }[];
  count: number;
}

export default async function getSharedTasks(
  token: string,
): Promise<SharedTaskData | undefined> {
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/action-items/shared/${token}`, {
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-cache',
    });
    if (!response.ok) {
      return undefined;
    }
    return (await response.json()) as SharedTaskData;
  } catch (err) {
    return undefined;
  }
}

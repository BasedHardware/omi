'use server';
import envConfig from '@/src/constants/envConfig';

const DESKTOP_API_URL = envConfig.DESKTOP_API_URL;

export interface SharedTaskInfo {
  description: string;
  due_at: string | null;
}

export interface SharedTasksResponse {
  sender_name: string;
  tasks: SharedTaskInfo[];
  count: number;
}

export default async function getSharedTasks(token: string): Promise<SharedTasksResponse | undefined> {
  try {
    const response = await fetch(`${DESKTOP_API_URL}/v1/action-items/shared/${token}`, {
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-cache',
    });
    if (!response.ok) {
      return undefined;
    }
    return (await response.json()) as SharedTasksResponse;
  } catch (err) {
    return undefined;
  }
}

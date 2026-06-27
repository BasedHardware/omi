'use server';

import envConfig from '@/src/constants/envConfig';

export interface SharedChatMessage {
  id: string;
  text: string;
  sender: string;
  created_at: string | null;
}

export interface SharedChatData {
  sender_name: string;
  messages: SharedChatMessage[];
  count: number;
}

export default async function getSharedChat(
  token: string,
): Promise<SharedChatData | undefined> {
  try {
    const response = await fetch(`${envConfig.API_URL}/v2/messages/shared/${token}`, {
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-cache',
    });

    if (!response.ok) {
      return undefined;
    }

    return (await response.json()) as SharedChatData;
  } catch {
    return undefined;
  }
}

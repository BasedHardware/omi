import { NextResponse } from 'next/server';
import { getDoc, doc } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import {
  PersonaAuthenticationError,
  PersonaGatewayUnavailableError,
  requestPersonaChatStream,
  resolvePersonaIdentity,
} from '@/lib/server/persona-chat-gateway.mjs';
import { buildPersonaSystemPrompt } from '@/lib/server/persona-chat-prompt.mjs';

export async function POST(req: Request) {
  try {
    const { message, botId, conversationHistory } = await req.json();

    let chatPrompt;

    if (
      typeof botId !== 'string' ||
      !botId ||
      typeof message !== 'string' ||
      !message.trim()
    ) {
      return NextResponse.json({ message: 'Bad param' }, { status: 400 });
    }

    try {
      const botDoc = await getDoc(doc(db, 'plugins_data', botId));
      if (botDoc.exists()) {
        const bot = botDoc.data();
        chatPrompt = bot.chat_prompt ?? bot.persona_prompt;
      }
    } catch (error) {
      console.error('Error fetching bot data:', error);
    }
    if (!chatPrompt)
      return NextResponse.json({ message: 'Persona not found' }, { status: 404 });

    const formattedMessages = [
      { role: 'system', content: buildPersonaSystemPrompt(chatPrompt) },
      ...(Array.isArray(conversationHistory) ? conversationHistory : [])
        .filter(
          (msg: unknown): msg is { sender: string; text: string } =>
            typeof msg === 'object' &&
            msg !== null &&
            typeof (msg as { sender?: unknown }).sender === 'string' &&
            typeof (msg as { text?: unknown }).text === 'string',
        )
        .map((msg: { sender: string; text: string }) => ({
          role: msg.sender === 'user' ? 'user' : 'assistant',
          content: msg.text,
        })),
      { role: 'user', content: message },
    ];

    const identity = await resolvePersonaIdentity(req.headers.get('authorization'));
    const gatewayResponse = await requestPersonaChatStream({
      identity,
      messages: formattedMessages,
    });

    return new Response(gatewayResponse.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (error: unknown) {
    if (error instanceof PersonaAuthenticationError) {
      return NextResponse.json({ error: 'Invalid authentication' }, { status: 401 });
    }
    if (error instanceof PersonaGatewayUnavailableError) {
      return NextResponse.json(
        { error: 'Chat temporarily unavailable' },
        { status: 503 },
      );
    }
    console.error('Persona chat request failed', {
      errorType: error instanceof Error ? error.name : 'unknown',
    });
    return NextResponse.json({ error: 'Failed to get response' }, { status: 500 });
  }
}

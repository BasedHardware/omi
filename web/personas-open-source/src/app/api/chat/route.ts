import { NextResponse } from 'next/server';
import { getDoc, doc } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import OpenAI from 'openai';

const getOpenAIClient = () => {
  return new OpenAI({
    baseURL: "https://openrouter.ai/api/v1",
    apiKey: process.env.OPENROUTER_API_KEY || '',
    defaultHeaders: {
      "X-Title": "Omi Chat",
    }
  });
};

export async function POST(req: Request) {
  try {
    const { message, botId, conversationHistory } = await req.json();

    var chatPrompt;
    var isInfluencer = false;

    if (!botId) return NextResponse.json({ message: "Bad param" }, { status: 400 });

    try {
      const botDoc = await getDoc(doc(db, 'plugins_data', botId));
      if (botDoc.exists()) {
        const bot = botDoc.data();
        chatPrompt = bot.chat_prompt ?? bot.persona_prompt;
        isInfluencer = bot.is_influencer ?? false;
      }
    } catch (error) {
      console.error('Error fetching bot data:', error);
    }
    if (!chatPrompt) return NextResponse.json({ message: "Persona not found" }, { status: 404 });

    console.log('Received request:', {
      botId,
      message,
      chatPrompt,
      conversationHistoryLength: conversationHistory?.length
    });

    // Initialize the OpenAI client
    const openai = getOpenAIClient();

    // Format messages for OpenRouter - including system message in the array
    const formattedMessages = [
      { role: "system", content: chatPrompt },
      ...(conversationHistory || []).map((msg: { sender: string; text: string; }) => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text
      })),
      { role: "user", content: message }
    ];

    console.log('Formatted messages:', formattedMessages);


    // LLM model, use a better model for specific people
    var llmModel = "google/gemini-flash-1.5-8b";
    if (isInfluencer) {
      llmModel = "anthropic/claude-3.5-sonnet";
    }

    const stream = await openai.chat.completions.create({
      model: llmModel,
      messages: formattedMessages,
      stream: true,
      temperature: 0.8,
      max_tokens: 2044,
    });

    // Set up streaming response
    const encoder = new TextEncoder();
    const customStream = new ReadableStream({
      async start(controller) {
        try {
          for await (const chunk of stream) {
            const content = chunk.choices[0]?.delta?.content || '';
            if (content) {
              const jsonString = JSON.stringify({ text: content });
              controller.enqueue(encoder.encode(`data: ${jsonString}\n\n`));
            }
          }
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        } catch (error) {
          controller.error(error);
        }
      }
    });

    return new Response(customStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });

  } catch (error: any) {
    console.error('Error in chat route:', error);
    console.error('Error details:', {
      message: error.message,
      stack: error.stack,
      response: error.response?.data
    });

    return NextResponse.json({
      error: 'Failed to get response',
      details: error.message || 'Unknown error',
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
    }, { status: 500 });
  }
}

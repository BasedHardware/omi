'use server';

import envConfig from '@/src/constants/envConfig';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatWithMemoryRequest {
  messages: ChatMessage[];
  transcript: string;
}

export interface ChatWithMemoryResponse {
  message: string;
}

const OPENAI_API_KEY = envConfig.OPENAI_API_KEY;

if (!OPENAI_API_KEY) {
  throw new Error('OPENAI_API_KEY is not configured. Please set it in your environment variables.');
}

// Rough token estimation: ~4 characters per token
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// Truncate transcript to fit within token budget
function truncateTranscript(transcript: string, maxTokens: number): string {
  const estimatedTokens = estimateTokens(transcript);
  if (estimatedTokens <= maxTokens) {
    return transcript;
  }

  // If transcript is too long, take the beginning and end
  const targetLength = maxTokens * 4; // Convert tokens back to characters
  const startLength = Math.floor(targetLength * 0.6); // 60% from start
  const endLength = Math.floor(targetLength * 0.4); // 40% from end

  const start = transcript.substring(0, startLength);
  const end = transcript.substring(transcript.length - endLength);

  return `${start}\n\n[... transcript truncated ...]\n\n${end}`;
}

export default async function chatWithMemory(
  data: ChatWithMemoryRequest,
): Promise<ChatWithMemoryResponse | null> {
  try {
    // Use gpt-4.1 which has 128k context window, or fallback to gpt-3.5-turbo-16k
    const model = 'gpt-4.1';
    
    // Estimate tokens for conversation messages (reserve ~2000 tokens for system message and response)
    const conversationTokens = data.messages.reduce(
      (sum, msg) => sum + estimateTokens(msg.content),
      0
    );
    
    // Reserve tokens: 2000 for system message overhead, 2000 for response, 2000 for conversation
    const maxTranscriptTokens = 120000 - conversationTokens - 2000 - 2000;
    
    // Truncate transcript if needed
    const processedTranscript = truncateTranscript(data.transcript, maxTranscriptTokens);

    // Create system message with transcript context
    const systemMessage = {
      role: 'system' as const,
      content: `You are a helpful chatbot assistant. You have access to the following conversation transcript. Use this context to answer questions accurately and helpfully.

Important: As a chatbot, provide short and concise answers. Be direct and to the point while still being helpful.

Critical: Always try to reference things from the conversation transcript, even when the user asks questions that seem unrelated to the conversation. Find connections, examples, or relevant details from the transcript that relate to their question, and incorporate those references into your response.

Transcript:
${processedTranscript}

Please answer questions based on the transcript above. Even if a question seems unrelated, always try to find and reference relevant information from the conversation.`,
    };

    // Keep only recent conversation messages to avoid token limit issues
    // Keep last 10 messages (5 exchanges) to maintain context
    const recentMessages = data.messages.slice(-10);
    const messages = [systemMessage, ...recentMessages];

    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OPENAI_API_KEY}`,
      },
      body: JSON.stringify({
        model: model,
        messages: messages,
        temperature: 0.7,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('OpenAI API error:', response.status, errorData);
      
      // If context length error, try with gpt-3.5-turbo-16k as fallback
      if (errorData.error?.code === 'context_length_exceeded') {
        const fallbackModel = 'gpt-3.5-turbo-16k';
        const fallbackMaxTokens = 14000 - conversationTokens - 2000 - 2000;
        const fallbackTranscript = truncateTranscript(data.transcript, fallbackMaxTokens);
        
        const fallbackSystemMessage = {
          role: 'system' as const,
          content: `You are a helpful chatbot assistant. You have access to the following conversation transcript. Use this context to answer questions accurately and helpfully.

Important: As a chatbot, provide short and concise answers. Be direct and to the point while still being helpful.

Critical: Always try to reference things from the conversation transcript, even when the user asks questions that seem unrelated to the conversation. Find connections, examples, or relevant details from the transcript that relate to their question, and incorporate those references into your response.

Try to say things like "like mentioned by x"

Transcript:
${fallbackTranscript}

Please answer questions based on the transcript above. Even if a question seems unrelated, always try to find and reference relevant information from the conversation.`,
        };

        const fallbackResponse = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${OPENAI_API_KEY}`,
          },
          body: JSON.stringify({
            model: fallbackModel,
            messages: [fallbackSystemMessage, ...recentMessages],
            temperature: 0.7,
          }),
        });

        if (!fallbackResponse.ok) {
          const fallbackErrorData = await fallbackResponse.json().catch(() => ({}));
          console.error('OpenAI API fallback error:', fallbackResponse.status, fallbackErrorData);
          return null;
        }

        const fallbackResult = await fallbackResponse.json();
        const assistantMessage = fallbackResult.choices[0]?.message?.content || 'Sorry, I could not generate a response.';
        return { message: assistantMessage };
      }
      
      return null;
    }

    const result = await response.json();
    const assistantMessage = result.choices[0]?.message?.content || 'Sorry, I could not generate a response.';

    return {
      message: assistantMessage,
    };
  } catch (error) {
    console.error('Error chatting with memory:', error);
    return null;
  }
}


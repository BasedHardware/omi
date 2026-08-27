import type { ServerMessage, MessageChunk, MessageChunkType } from '@/types/conversation';

/**
 * Decode base64 string to UTF-8 text
 */
function decodeBase64Utf8(base64: string): string {
  try {
    // Decode base64 to binary string
    const binaryString = atob(base64);
    // Convert binary string to Uint8Array
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    // Decode as UTF-8
    const decoder = new TextDecoder('utf-8');
    return decoder.decode(bytes);
  } catch (e) {
    console.error('Failed to decode base64 UTF-8:', e);
    // Fallback to simple atob
    return atob(base64);
  }
}

/**
 * Parse a streaming response line into a MessageChunk
 */
export function parseStreamLine(line: string): MessageChunk | null {
  if (!line || line.trim() === '') return null;

  if (line.startsWith('think: ')) {
    return {
      type: 'think' as MessageChunkType,
      text: line.slice(7).replace(/__CRLF__/g, '\n'),
    };
  }
  if (line.startsWith('data: ')) {
    return {
      type: 'data' as MessageChunkType,
      text: line.slice(6).replace(/__CRLF__/g, '\n'),
    };
  }
  if (line.startsWith('done: ')) {
    try {
      const decoded = decodeBase64Utf8(line.slice(6));
      const message = JSON.parse(decoded) as ServerMessage;
      return {
        type: 'done' as MessageChunkType,
        text: decoded,
        message,
      };
    } catch (e) {
      console.error('Failed to parse done chunk:', e);
      return null;
    }
  }
  if (line.startsWith('message: ')) {
    try {
      const decoded = decodeBase64Utf8(line.slice(9));
      const message = JSON.parse(decoded) as ServerMessage;
      return {
        type: 'message' as MessageChunkType,
        text: decoded,
        message,
      };
    } catch (e) {
      console.error('Failed to parse message chunk:', e);
      return null;
    }
  }
  if (line.startsWith('error: ')) {
    return {
      type: 'error' as MessageChunkType,
      text: line.slice(7),
    };
  }

  return null;
}

/**
 * Gemini API client for image analysis.
 * TypeScript port of the macOS GeminiClient.swift
 */

// Types matching Gemini API
interface GeminiRequestPart {
    text?: string;
    inline_data?: {
        mime_type: string;
        data: string;
    };
}

interface GeminiRequestContent {
    parts: GeminiRequestPart[];
}

interface GeminiRequest {
    contents: GeminiRequestContent[];
    system_instruction?: {
        parts: { text: string }[];
    };
    generation_config?: {
        response_mime_type: string;
        response_schema?: GeminiResponseSchema;
    };
}

export interface GeminiResponseSchema {
    type: string;
    properties: Record<string, GeminiPropertySchema>;
    required: string[];
}

export interface GeminiPropertySchema {
    type: string;
    enum?: string[];
    description?: string;
    items?: {
        type: string;
        properties?: Record<string, GeminiPropertySchema>;
        required?: string[];
    };
    properties?: Record<string, GeminiPropertySchema>;
    required?: string[];
}

interface GeminiResponse {
    candidates?: {
        content?: {
            parts?: { text?: string }[];
        };
    }[];
    error?: {
        message: string;
    };
}

export class GeminiClientError extends Error {
    constructor(
        public code: 'MISSING_API_KEY' | 'NETWORK_ERROR' | 'INVALID_RESPONSE' | 'API_ERROR',
        message: string
    ) {
        super(message);
        this.name = 'GeminiClientError';
    }
}

const DEFAULT_MODEL = 'gemini-2.0-flash';

/**
 * Send an image analysis request to Gemini API
 */
export async function sendImageRequest(
    apiKey: string,
    prompt: string,
    imageData: Blob,
    systemPrompt: string,
    responseSchema?: GeminiResponseSchema,
    model: string = DEFAULT_MODEL
): Promise<string> {
    if (!apiKey) {
        throw new GeminiClientError('MISSING_API_KEY', 'Gemini API key is required');
    }

    // Convert blob to base64
    const base64Data = await blobToBase64(imageData);

    const request: GeminiRequest = {
        contents: [
            {
                parts: [
                    { text: prompt },
                    {
                        inline_data: {
                            mime_type: 'image/jpeg',
                            data: base64Data,
                        },
                    },
                ],
            },
        ],
        system_instruction: {
            parts: [{ text: systemPrompt }],
        },
    };

    if (responseSchema) {
        request.generation_config = {
            response_mime_type: 'application/json',
            response_schema: responseSchema,
        };
    }

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(request),
        });

        const data = (await response.json()) as GeminiResponse;

        if (data.error) {
            throw new GeminiClientError('API_ERROR', data.error.message);
        }

        const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!text) {
            throw new GeminiClientError('INVALID_RESPONSE', 'No text in response from Gemini API');
        }

        return text;
    } catch (err) {
        if (err instanceof GeminiClientError) {
            throw err;
        }
        const message = err instanceof Error ? err.message : 'Unknown error';
        throw new GeminiClientError('NETWORK_ERROR', `Network error: ${message}`);
    }
}

/**
 * Convert Blob to base64 string (without data URL prefix)
 */
export function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const dataUrl = reader.result as string;
            // Remove the "data:image/jpeg;base64," prefix
            const base64 = dataUrl.split(',')[1];
            resolve(base64);
        };
        reader.onerror = () => reject(new Error('Failed to read blob'));
        reader.readAsDataURL(blob);
    });
}

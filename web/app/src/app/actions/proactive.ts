'use server';

import { GeminiResponseSchema } from '@/lib/geminiClient';

interface AnalyzeScreenParams {
    imageBase64: string;
    imageMimeType?: string;
    prompt: string;
    systemPrompt: string;
    responseSchema?: GeminiResponseSchema;
    model?: string;
}

const DEFAULT_MODEL = 'gemini-2.0-flash';
const ALLOWED_MODELS = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'];

export async function analyzeScreenAction(params: AnalyzeScreenParams): Promise<string> {
    const apiKey = process.env.GEMINI_API_KEY || process.env.NEXT_PUBLIC_GEMINI_API_KEY;

    if (!apiKey) {
        throw new Error('Gemini API key not configured on server');
    }

    const {
        imageBase64,
        imageMimeType = 'image/jpeg',
        prompt,
        systemPrompt,
        responseSchema,
        model = DEFAULT_MODEL
    } = params;

    // Validate model
    if (!ALLOWED_MODELS.includes(model)) {
        throw new Error(`Invalid model specified. Allowed: ${ALLOWED_MODELS.join(', ')}`);
    }

    // Construct request payload
    const requestBody: any = {
        contents: [
            {
                parts: [
                    { text: prompt },
                    {
                        inline_data: {
                            mime_type: imageMimeType,
                            data: imageBase64,
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
        requestBody.generation_config = {
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
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Gemini API error: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error.message);
        }

        const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!text) {
            throw new Error('No text in response from Gemini API');
        }

        return text;
    } catch (error: any) {
        console.error('Server Action Analysis Failed:', error);
        throw new Error(error.message || 'Analysis failed');
    }
}

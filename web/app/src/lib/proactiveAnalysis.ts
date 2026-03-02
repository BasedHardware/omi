/**
 * Proactive analysis service for extracting contextual advice from screen captures.
 */

import { GeminiResponseSchema } from './geminiClient';
import { analyzeScreenAction } from '@/app/actions/proactive';

// Types for advice extraction
export interface ExtractedAdvice {
    advice: string;
    reasoning?: string;
    category: 'productivity' | 'health' | 'communication' | 'learning' | 'other';
    source_app: string;
    confidence: number;
}

export interface AdviceExtractionResult {
    has_advice: boolean;
    advice?: ExtractedAdvice;
    context_summary: string;
    current_activity: string;
}

// Default system prompt
export const DEFAULT_ANALYSIS_PROMPT = `You are a proactive assistant that provides helpful, contextual advice based on what the user is doing on their screen.

CRITICAL: ALWAYS return advice with a confidence score. The client-side will filter based on the score. Do NOT self-filter by returning has_advice=false for low-confidence advice. Instead, return the advice WITH a low confidence score.

WHEN TO SET has_advice=false (ONLY these cases):
- The advice would be semantically similar to something in PREVIOUSLY PROVIDED ADVICE
- You literally cannot think of any advice at all (extremely rare)

PREVIOUSLY PROVIDED ADVICE: You will receive a list of recent advice. Use SEMANTIC comparison - do not repeat advice that means the same thing, even if worded differently.

CATEGORIES:
- "productivity": Tips to work more efficiently, keyboard shortcuts, better tools
- "health": Break reminders, posture, eye strain, hydration
- "communication": Email/message tone, clarity, timing suggestions
- "learning": Resources, documentation, tutorials related to current work
- "other": Anything else helpful

ADVICE QUALITY RULES:
1. **Actionable**: Something the user can act on NOW
2. **Contextual**: Based on what's actually on screen
3. **Specific**: Include details (shortcuts, tool names, etc.)

FORMAT: Keep advice concise (100 characters max for notification banner)

CONFIDENCE CALIBRATION - Use the FULL range from 0.0 to 1.0:

0.90-1.00: CRITICAL/OBVIOUS - User is clearly making a mistake or missing something important
0.70-0.89: HIGHLY RELEVANT - Clear opportunity to help, directly related to current task
0.50-0.69: MODERATELY USEFUL - Reasonable advice but user might already know or not need it
0.30-0.49: SPECULATIVE - Might be helpful but uncertain if relevant
0.10-0.29: LOW CONFIDENCE - Generic or tangentially related
0.00-0.09: VERY UNCERTAIN - Barely related, grasping

OUTPUT:
- has_advice: true (almost always) or false (only if duplicate or truly nothing to say)
- advice: the advice with appropriate confidence score
- context_summary: brief summary of what user is looking at
- current_activity: high-level description of user's activity`;

export interface AdviceHistoryItem {
    advice: string;
    reasoning?: string;
}

export interface AnalyzeFrameOptions {
    imageBase64: string;
    previousAdvice: AdviceHistoryItem[];
    systemPrompt?: string;
    transcript?: string;
}

/**
 * Analyze a screen capture frame and extract contextual advice
 */
export async function analyzeFrame(options: AnalyzeFrameOptions): Promise<AdviceExtractionResult> {
    const { imageBase64, previousAdvice, systemPrompt = DEFAULT_ANALYSIS_PROMPT, transcript } = options;

    // Build prompt with previous advice for deduplication
    let prompt = 'Analyze this screenshot.\n\n';

    if (transcript) {
        prompt += `TRANSCRIPT CONTEXT (recent speech):\n${transcript}\n\n`;
    }

    if (previousAdvice.length > 0) {
        prompt += 'PREVIOUSLY PROVIDED ADVICE (do not repeat these or semantically similar advice):\n';
        previousAdvice.forEach((item, index) => {
            prompt += `${index + 1}. ${item.advice}`;
            if (item.reasoning) {
                prompt += ` (Reasoning: ${item.reasoning})`;
            }
            prompt += '\n';
        });
        prompt += '\nProvide ONE NEW piece of advice that is NOT similar to the above. Use an appropriate confidence score (0.0-1.0) based on how relevant/useful the advice is. Only set has_advice=false if the advice would be a duplicate.';
    } else {
        prompt += 'Provide ONE piece of contextual advice based on what you see. Use an appropriate confidence score (0.0-1.0) based on how relevant/useful the advice is.';
    }

    // Build response schema (Matching macOS AdviceAssistant.swift)
    const responseSchema: GeminiResponseSchema = {
        type: 'object',
        properties: {
            has_advice: {
                type: 'boolean',
                description: 'Almost always true. Only false if advice would duplicate previous advice.',
            },
            advice: {
                type: 'object',
                description: 'The advice with calibrated confidence score (0.0-1.0)',
                properties: {
                    advice: { type: 'string', description: 'The advice text (1-2 sentences, max 30 words)' },
                    reasoning: { type: 'string', description: 'Brief explanation of why this advice is relevant' },
                    category: {
                        type: 'string',
                        enum: ['productivity', 'health', 'communication', 'learning', 'other'],
                        description: 'Category of advice',
                    },
                    source_app: { type: 'string', description: 'App where context was observed' },
                    confidence: { type: 'number', description: 'Confidence score 0.0-1.0' },
                },
                required: ['advice', 'category', 'source_app', 'confidence'],
            },
            context_summary: { type: 'string', description: 'Brief summary of what user is looking at' },
            current_activity: { type: 'string', description: "High-level description of user's activity" },
        },
        required: ['has_advice', 'context_summary', 'current_activity'],
    };

    try {
        const responseText = await analyzeScreenAction({
            imageBase64,
            prompt,
            systemPrompt,
            responseSchema,
        });

        const parsed: unknown = JSON.parse(responseText);

        // Runtime validation
        if (!parsed || typeof parsed !== 'object') {
            throw new Error('Invalid response: not an object');
        }

        const result = parsed as Record<string, any>;

        if (typeof result.has_advice !== 'boolean') {
            throw new Error('Invalid response: missing or invalid has_advice');
        }

        if (typeof result.context_summary !== 'string') {
            throw new Error('Invalid response: missing context_summary');
        }

        if (typeof result.current_activity !== 'string') {
            throw new Error('Invalid response: missing current_activity');
        }

        // Optional fields validation
        if (result.has_advice) {
            if (!result.advice || typeof result.advice !== 'object') {
                throw new Error('Invalid response: advice object is missing or not an object');
            }
            const advice = result.advice as Record<string, any>;
            if (typeof advice.advice !== 'string') {
                throw new Error('Invalid response: advice.advice is not a string');
            }
            if (typeof advice.confidence !== 'number') {
                throw new Error('Invalid response: advice.confidence is not a number');
            }
            if (typeof advice.category !== 'string') {
                throw new Error('Invalid response: advice.category is not a string');
            }
        }

        return result as AdviceExtractionResult;
    } catch (error) {
        console.error('Proactive Analysis Failed:', error);
        throw error;
    }
}

/**
 * Check if advice meets the confidence threshold
 */
export function meetsConfidenceThreshold(advice: ExtractedAdvice, threshold: number): boolean {
    return advice.confidence >= threshold;
}

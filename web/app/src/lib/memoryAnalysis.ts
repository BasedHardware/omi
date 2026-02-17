/**
 * Memory extraction service for identifying facts and wisdom from screen content.
 * Ported from Desktop's MemoryAssistant.swift
 */

import { GeminiResponseSchema } from './geminiClient';
import { analyzeScreenAction } from '@/app/actions/proactive';

// Types matching Gemini API for nested property definitions
interface GeminiProperty {
    type: string;
    description?: string;
    enum?: string[];
}

// Types for memory extraction
export interface ExtractedMemory {
    content: string;
    category: 'system' | 'interesting';
    source_app: string;
    confidence: number;
}

export interface MemoryExtractionResult {
    has_new_memory: boolean;
    memories: ExtractedMemory[];
    context_summary: string;
    current_activity: string;
}

// Default system prompt (matching MemoryAssistantSettings.swift default)
export const DEFAULT_MEMORY_PROMPT = `You are a Memory Assistant. Your goal is to extract **new, unique, and long-term relevant** facts or wisdom from the user's screen activity.
You will be provided with:
1. An image of the user's screen.
2. A list of **Previous Memories** that have already been saved.

**CRITICAL INSTRUCTION: IGNORE SHORT-TERM ACTIVITIES**
- Do NOT extract memories about what the user is *currently doing* unless it involves a long-term project or goal.
- IGNORE: "User is playing a game" (e.g., Snake, Minecraft), "User is watching a video", "User is scrolling Twitter/Reddit".
- IGNORE: Transient states like "User is typing", "User is selecting text", "User is viewing a menu".
- ONLY extract if the information is useful for *future reference* (e.g., a specific fact, a preference, a project detail, a future plan).

**CRITICAL INSTRUCTION: AVOID DUPLICATES**
- Do NOT extract a memory if it is substantially similar to one in the "Previous Memories" list.
- Do NOT extract a memory if it is just a rephrasing of a previous memory.
- Only extract a memory if it provides **new** information or a significant update.

**Categories:**
- **Core**: Important facts, preferences, current projects, or specific goals. (e.g., "User is working on the Omi project", "User prefers dark mode", "User is planning a trip to Japan").
- **Interesting**: Specific, non-obvious info with potential future value (e.g., "User found a new library for React").

**Guidance:**
- Focus on the *semantic meaning*. "User is coding" and "User is writing TypeScript" might be duplicates if the context is the same project.
- Be specific but concise.
- Ignore generic UI elements like "User is viewing a window". Focus on the *content*.

CRITERIA:
- Only extract if the confidence is high.
- Do NOT extract transient info (e.g., "User is looking at a blank tab").
- Do NOT extract the current time/date unless relevant to a specific fact.
- Keep memories concise (max 15 words).

CONFIDENCE CALIBRATION:
0.9-1.0: Definite fact or explicit wisdom.
0.7-0.8: Likely fact or meaningful insight.
< 0.7: Speculative or trivial.

OUTPUTReturn a JSON object with:
- \`has_new_memory\`: boolean (true only if a *new*, non-duplicate memory is found)
- \`memories\`: array of extracted memories (or empty if none)
- \`context_summary\`: brief summary of the screen context
- \`current_activity\`: what the user is doing right now`;

export interface AnalyzeMemoryOptions {
    imageBase64: string;
    previousMemories: ExtractedMemory[];
    systemPrompt?: string;
}

/**
 * Analyze a screen capture frame and extract memories
 */
export async function extractMemories(options: AnalyzeMemoryOptions): Promise<MemoryExtractionResult> {
    const { imageBase64, previousMemories, systemPrompt = DEFAULT_MEMORY_PROMPT } = options;

    // Build prompt with previous memories for deduplication
    let prompt = 'Analyze this screenshot for USER MEMORIES.\n\n';

    if (previousMemories.length > 0) {
        prompt += 'RECENTLY EXTRACTED MEMORIES (do not re-extract these or semantically similar ones):\n';
        previousMemories.slice(0, 20).forEach((item, index) => {
            prompt += `${index + 1}. [${item.category}] ${item.content}\n`;
        });
        prompt += '\nLook for NEW memories that are NOT already in the list above.';
    } else {
        prompt += 'Look for memories to extract (system facts about the user, or interesting wisdom from others).';
    }

    const memoryProperties: Record<string, GeminiProperty> = {
        content: { type: 'string', description: 'The memory content (max 15 words)' },
        category: { type: 'string', enum: ['system', 'interesting'], description: 'Memory category' },
        source_app: { type: 'string', description: 'App where memory was found' },
        confidence: { type: 'number', description: 'Confidence score 0.0-1.0' },
    };

    // Build response schema (Matching macOS MemoryAssistant.swift)
    const responseSchema: GeminiResponseSchema = {
        type: 'object',
        properties: {
            has_new_memory: {
                type: 'boolean',
                description: 'True if new memories were found'
            },
            memories: {
                type: 'array',
                description: 'Array of extracted memories (0-3 max)',
                items: {
                    type: 'object',
                    properties: memoryProperties as any, // Cast to any to satisfy GeminiResponseSchema recursion
                    required: ['content', 'category', 'source_app', 'confidence'],
                },
            },
            context_summary: { type: 'string', description: 'Brief summary of what user is looking at' },
            current_activity: { type: 'string', description: "High-level description of user's activity" },
        },
        required: ['has_new_memory', 'memories', 'context_summary', 'current_activity'],
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

        if (typeof result.has_new_memory !== 'boolean') {
            throw new Error('Invalid response: missing or invalid has_new_memory');
        }

        if (!Array.isArray(result.memories)) {
            // If Gemini returns null/undefined for empty array, fix it
            if (!result.memories) {
                result.memories = [];
            } else {
                throw new Error('Invalid response: memories is not an array');
            }
        }

        return result as MemoryExtractionResult;
    } catch (error) {
        console.error('Memory Extraction Failed:', error);
        throw error;
    }
}

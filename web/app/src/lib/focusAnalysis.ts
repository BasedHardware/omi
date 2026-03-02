import { GeminiResponseSchema } from './geminiClient';
import { analyzeScreenAction } from '@/app/actions/proactive';

// Types for focus analysis
export type FocusStatus = 'focused' | 'distracted';

export interface FocusAnalysisResult {
    status: FocusStatus;
    app_or_site: string;
    description: string;
    message?: string; // Coaching message
}

export interface FocusHistoryItem extends FocusAnalysisResult {
    timestamp: number;
}

export interface AnalysisHistoryItem {
    status: string;
    app_or_site: string;
    description: string;
    message?: string;
}

// System prompt
export const DEFAULT_FOCUS_SYSTEM_PROMPT = `You are a Focus Coach. Your goal is to help the user stay focused on their work and avoid distractions.
Analyze the screenshot to determine if the user is "focused" or "distracted".

- "focused": User is doing productive work (coding, writing, reading docs, designing, emails, etc.)
- "distracted": User is on social media, shopping, browsing random videos/memes, or gaming (unless it looks like work).

Return a JSON with:
- "status": "focused" or "distracted"
- "app_or_site": Name of the app or website visible
- "description": Brief description of what they are doing
- "message": A SHORT, encouraging coaching message if distracted (e.g., "Let's get back to the project", "Time to refocus?"). If focused, you can optionally give a brief "Good job" or return null.

Be lenient. If unsure, assume focused.
`;

export interface AnalyzeFocusOptions {
    imageBase64: string;
    analysisHistory: AnalysisHistoryItem[];
    systemPrompt?: string;
    transcript?: string;
}

function formatHistory(history: AnalysisHistoryItem[]): string {
    if (!history || history.length === 0) return "";

    let lines = ["Recent activity (oldest to newest):"];
    history.forEach((past, i) => {
        lines.push(`${i + 1}. [${past.status}] ${past.app_or_site}: ${past.description}`);
        if (past.message) {
            lines.push(`   Message: ${past.message}`);
        }
    });
    return lines.join("\n");
}

export async function analyzeFocus(options: AnalyzeFocusOptions): Promise<FocusAnalysisResult> {
    const {
        imageBase64,
        systemPrompt = DEFAULT_FOCUS_SYSTEM_PROMPT,
        transcript,
        analysisHistory = []
    } = options;

    // Build prompt with history context (Matching macOS FocusAssistant.swift)
    const historyText = formatHistory(analysisHistory);
    let prompt = historyText === "" ? "Analyze this screenshot:" : `${historyText}\n\nNow analyze this new screenshot:`;

    if (transcript) {
        prompt += `\n\nTRANSCRIPT CONTEXT:\n${transcript}\n`;
    }

    // Build response schema (Matching macOS FocusAssistant.swift)
    const responseSchema: GeminiResponseSchema = {
        type: "object",
        properties: {
            status: {
                type: "string",
                enum: ["focused", "distracted"],
                description: "Whether the user is focused or distracted"
            },
            app_or_site: { type: "string", description: "The app or website visible" },
            description: { type: "string", description: "Brief description of what's on screen" },
            message: { type: "string", description: "Coaching message" }
        },
        required: ["status", "app_or_site", "description"]
    };

    try {
        const responseText = await analyzeScreenAction({
            imageBase64,
            prompt,
            systemPrompt,
            responseSchema
        });

        const parsed: unknown = JSON.parse(responseText);

        // Runtime validation
        if (!parsed || typeof parsed !== 'object') {
            throw new Error('Invalid response: not an object');
        }

        const result = parsed as Record<string, any>;

        if (typeof result.status !== 'string' || !['focused', 'distracted'].includes(result.status)) {
            throw new Error('Invalid response: missing or invalid status');
        }

        if (typeof result.app_or_site !== 'string') {
            throw new Error('Invalid response: missing app_or_site');
        }

        if (typeof result.description !== 'string') {
            throw new Error('Invalid response: missing description');
        }

        // message is optional
        if (result.message !== undefined && typeof result.message !== 'string') {
            throw new Error('Invalid response: message must be string if present');
        }

        return result as FocusAnalysisResult;
    } catch (error) {
        console.error('Focus Analysis Failed:', error);
        throw error;
    }
}

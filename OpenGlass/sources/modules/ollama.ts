import axios from 'axios';
import { backoff } from "../utils/time";
import { trimIdent } from '../utils/trimIdent';
import { toBase64 } from '../utils/base64';
import { keys } from '../keys';

// export const ollama = new Ollama({ host: 'https://ai-1.korshakov.com' });

export type KnownModel =
    | 'llama3'
    | 'llama3-gradient'
    | 'llama3:8b-instruct-fp16'
    | 'llava-llama3'
    | 'llava:34b-v1.6'
    | 'moondream:1.8b-v2-fp16'
    | 'moondream:1.8b-v2-moondream2-text-model-f16'

export async function ollamaInference(args: {
    model: KnownModel,
    messages: { role: 'system' | 'user' | 'assistant', content: string, images?: Uint8Array[] }[],
}) {
    const response = await backoff<any>(async () => {

        let converted: { role: string, content: string, images?: string[] }[] = [];
        for (let message of args.messages) {
            converted.push({
                role: message.role,
                content: trimIdent(message.content),
                images: message.images ? message.images.map((image) => toBase64(image)) : undefined,
            });
        }

        let resp = await axios.post(keys.ollama, {
            stream: false,
            model: args.model,
            messages: converted,
        });
        return resp.data;
    });
    return trimIdent(((response.message?.content ?? '') as string));
}
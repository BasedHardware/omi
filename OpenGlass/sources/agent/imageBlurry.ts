import { ollamaInference } from "../modules/ollama";

export async function imageBlurry(src: Uint8Array): Promise<string> {
    return ollamaInference({
        model: 'moondream:1.8b-v2-moondream2-text-model-f16',
        messages: [{
            role: 'system',
            content: 'You are an very advanced model and your task is to determine if the image is broken, blurry or just low quality. You must always answer as YES or NO.'
        }, {
            role: 'user',
            content: 'Is this image blurry, broken or low quality? YES or NO.',
            images: [src],
        }]
    });
}
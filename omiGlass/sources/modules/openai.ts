import axios from "axios";
import { keys } from "../keys";

let audioContext: AudioContext;

export async function startAudio() {
    audioContext = new AudioContext();
}

export async function textToSpeech(text: string) {
    try {
        const response = await axios.post("https://api.openai.com/v1/audio/speech", {
            input: text,    // Use 'input' instead of 'text'
            voice: "nova",
            model: "tts-1",
        }, {
            headers: {
                'Authorization': `Bearer ${keys.openai}`,  // Replace YOUR_API_KEY with your actual OpenAI API key
                'Content-Type': 'application/json'
            },
            responseType: 'arraybuffer'  // This will handle the binary data correctly
        });


        // Decode the audio data asynchronously
        const audioBuffer = await audioContext.decodeAudioData(response.data);

        // Create an audio source
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start();  // Play the audio immediately

        return response.data;
    } catch (error) {
        console.error("Error in textToSpeech:", error);
        return null; // or handle error differently
    }
}

import axios from "axios";
import * as FileSystem from 'expo-file-system';
import { Platform } from 'react-native';
import { keys } from "../keys";

function blobToBase64(blob: Blob | File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const result = reader.result as string;
            // Remove the data URL prefix to get just the base64 string
            const base64 = result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}


export async function transcribeAudio(audioInput: string | File | Blob) {
    let audioBase64: string;
    
    if (Platform.OS === 'web') {
        if (typeof audioInput === 'string') {
            // If it's a URL, fetch it first
            const response = await fetch(audioInput);
            const blob = await response.blob();
            audioBase64 = await blobToBase64(blob);
        } else {
            // If it's a File or Blob object
            audioBase64 = await blobToBase64(audioInput as Blob);
        }
    } else {
        // Mobile: expect a file path string
        audioBase64 = await FileSystem.readAsStringAsync(audioInput as string, { 
            encoding: FileSystem.EncodingType.Base64 
        });
    }
    
    try {
        const response = await axios.post("https://api.openai.com/v1/audio/transcriptions", {
            audio: audioBase64,
        }, {
            headers: {
                'Authorization': `Bearer ${keys.openai}`,  // Replace YOUR_API_KEY with your actual OpenAI API key
                'Content-Type': 'application/json'
            },
        });
        return response.data;
    } catch (error) {
        console.error("Error in transcribeAudio:", error);
        return null; // or handle error differently
    }
}

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

// Function to convert image to base64
async function imageToBase64(imageInput: string | File | Blob): Promise<string> {
    let base64: string;
    
    if (Platform.OS === 'web') {
        if (typeof imageInput === 'string') {
            // If it's a URL, fetch it first
            const response = await fetch(imageInput);
            const blob = await response.blob();
            base64 = await blobToBase64(blob);
        } else {
            // If it's a File or Blob object
            base64 = await blobToBase64(imageInput as Blob);
        }
        
        // Determine MIME type for web
        const mimeType = (imageInput as File)?.type || 'image/jpeg';
        return `data:${mimeType};base64,${base64}`;
    } else {
        // Mobile: expect a file path string
        const image = await FileSystem.readAsStringAsync(imageInput as string, { 
            encoding: FileSystem.EncodingType.Base64 
        });
        return `data:image/jpeg;base64,${image}`;
    }
}

export async function describeImage(imageInput: string | File | Blob) {
    const imageBase64 = await imageToBase64(imageInput);
    try {
        const response = await axios.post("https://api.openai.com/v1/images/descriptions", {
            image: imageBase64,
        }, {
            headers: {
                'Authorization': `Bearer ${keys.openai}`,  // Replace YOUR_API_KEY with your actual OpenAI API key
                'Content-Type': 'application/json'
            },
        });
        return response.data;
    } catch (error) {
        console.error("Error in describeImage:", error);
        return null; // or handle error differently
    }
}

export async function gptRequest(systemPrompt: string, userPrompt: string) {
    try {
        const response = await axios.post("https://api.openai.com/v1/chat/completions", {
            model: "gpt-4o",
            messages: [
                { role: "system", content: systemPrompt },
                { role: "user", content: userPrompt },
            ],
        }, {
            headers: {
                'Authorization': `Bearer ${keys.openai}`,  // Replace YOUR_API_KEY with your actual OpenAI API key
                'Content-Type': 'application/json'
            },
        });
        return response.data;
    } catch (error) {
        console.error("Error in gptRequest:", error);
        return null; // or handle error differently
    }
}


textToSpeech("Hello I am an agent")
console.info(gptRequest(
    `
                You are a smart AI that need to read through description of a images and answer user's questions.

                This are the provided images:
                The image features a woman standing in an open space with a metal roof, possibly at a train station or another large building.
                She is wearing a hat and appears to be looking up towards the sky.
                The scene captures her attention as she gazes upwards, perhaps admiring something above her or simply enjoying the view from this elevated position.

                DO NOT mention the images, scenes or descriptions in your answer, just answer the question.
                DO NOT try to generalize or provide possible scenarios.
                ONLY use the information in the description of the images to answer the question.
                BE concise and specific.
            `
        ,
            'where is the person?'

))
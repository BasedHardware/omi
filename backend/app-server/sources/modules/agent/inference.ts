import axios from 'axios';

export async function whisper(url: string) {
    let output = await axios.post('http://inference.home:5000/service/whisper', { url });
    let lines = (output.data as string).split('\n').filter((v) => v.length !== 0).map((v) => JSON.parse(v));
    let text: string | null = null;
    for (let l of lines) {
        if (l.status === 'transcribed') {
            text = l.text;
        }
    }
    return text;
}
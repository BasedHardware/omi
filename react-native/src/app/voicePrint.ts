export const VOICE_PRINT_MIN_SECONDS = 5;
export const VOICE_PRINT_MAX_SECONDS = 180;
export const VOICE_PRINT_SAMPLE_RATE = 16000;

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

export function pcm16ToWav(
  pcm: Int16Array,
  sampleRate = VOICE_PRINT_SAMPLE_RATE,
): ArrayBuffer {
  const dataSize = pcm.byteLength;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataSize, true);
  new Uint8Array(buffer, 44).set(
    new Uint8Array(pcm.buffer, pcm.byteOffset, dataSize),
  );
  return buffer;
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const pcm = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm;
}

export function wavDurationSeconds(
  pcm: Int16Array,
  sampleRate = VOICE_PRINT_SAMPLE_RATE,
): number {
  return pcm.length / sampleRate;
}

export function assertVoicePrintDuration(seconds: number): void {
  if (seconds < VOICE_PRINT_MIN_SECONDS || seconds > VOICE_PRINT_MAX_SECONDS) {
    throw new Error('Talk for about 5 seconds so Omi can learn your voice.');
  }
}

type UploadAudio = (
  wav: ArrayBuffer,
  filename: string,
) => Promise<{status: number}>;

export async function uploadVoicePrint(
  upload: UploadAudio | null | undefined,
  wav: ArrayBuffer,
): Promise<void> {
  if (upload == null) {
    throw new Error('Voice print upload needs a signed-in session.');
  }
  const response = await upload(wav, 'speech_profile.wav');
  if (response.status === 401) {
    throw new Error('Sign in required');
  }
  if (response.status !== 200) {
    throw new Error(`Voice print could not be saved (${response.status})`);
  }
}

export async function recordVoicePrintWav(
  mediaDevices: {
    getUserMedia(constraints: {audio: boolean}): Promise<{
      getTracks(): Array<{stop(): void}>;
    }>;
  } | null,
  AudioContextCtor:
    | (new (options?: {sampleRate: number}) => {
        sampleRate: number;
        createMediaStreamSource(stream: unknown): {
          connect(node: unknown): void;
        };
        createScriptProcessor(
          bufferSize: number,
          inputChannels: number,
          outputChannels: number,
        ): {
          connect(node: unknown): void;
          disconnect(): void;
          onaudioprocess:
            | ((event: {
                inputBuffer: {getChannelData(channel: number): Float32Array};
              }) => void)
            | null;
        };
        destination: unknown;
        close(): Promise<void> | void;
      })
    | null,
  seconds: number,
): Promise<ArrayBuffer> {
  if (mediaDevices == null || AudioContextCtor == null) {
    throw new Error('Microphone capture is not available here.');
  }
  const stream = await mediaDevices.getUserMedia({audio: true});
  const context = new AudioContextCtor({sampleRate: VOICE_PRINT_SAMPLE_RATE});
  const chunks: Float32Array[] = [];
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = event => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };
  source.connect(processor);
  processor.connect(context.destination);
  await new Promise(resolve => setTimeout(resolve, seconds * 1000));
  processor.disconnect();
  for (const track of stream.getTracks()) {
    track.stop();
  }
  await context.close();
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    samples.set(chunk, offset);
    offset += chunk.length;
  }
  const pcm = floatToPcm16(samples);
  assertVoicePrintDuration(wavDurationSeconds(pcm, context.sampleRate));
  return pcm16ToWav(pcm, context.sampleRate);
}

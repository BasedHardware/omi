/**
 * Audio capture utilities for recording feature.
 * Handles microphone and system audio capture, mixing, and conversion to PCM 16kHz.
 */

export type AudioMode = 'mic-only' | 'mic-and-system';

export interface AudioCaptureOptions {
  mode: AudioMode;
  onAudioData: (pcmData: Int16Array) => void;
  onMicLevel: (level: number) => void;
  onSystemLevel: (level: number) => void;
  onError: (error: string) => void;
}

export interface AudioCapture {
  start: () => Promise<void>;
  stop: () => void;
  pause: () => void;
  resume: () => void;
}

// Target audio format for transcription
const TARGET_SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

/**
 * Get microphone stream
 */
export async function getMicrophoneStream(): Promise<MediaStream> {
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: { ideal: TARGET_SAMPLE_RATE },
      },
    });
  } catch (err) {
    if (err instanceof DOMException) {
      if (err.name === 'NotAllowedError') {
        throw new Error('Microphone access denied. Please allow microphone access and try again.');
      }
      if (err.name === 'NotFoundError') {
        throw new Error('No microphone found. Please connect a microphone and try again.');
      }
    }
    throw new Error('Failed to access microphone');
  }
}

/**
 * Get system audio stream via screen share
 */
export async function getSystemAudioStream(): Promise<MediaStream> {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true, // Required by browsers, we'll ignore the video track
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });

    // Check if we got audio
    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) {
      // Stop video track if no audio
      stream.getVideoTracks().forEach((track) => track.stop());
      throw new Error('No audio selected. Please share a tab with audio enabled.');
    }

    // Stop video track - we only need audio
    stream.getVideoTracks().forEach((track) => track.stop());

    return stream;
  } catch (err) {
    if (err instanceof DOMException) {
      if (err.name === 'NotAllowedError') {
        throw new Error('Screen share cancelled. System audio capture requires sharing a tab or window.');
      }
    }
    if (err instanceof Error && err.message.includes('No audio')) {
      throw err;
    }
    throw new Error('Failed to capture system audio');
  }
}

/**
 * Calculate audio level (0-1) from audio data
 */
function calculateLevel(data: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i] * data[i];
  }
  const rms = Math.sqrt(sum / data.length);
  // Convert to 0-1 range with some scaling for better visualization
  return Math.min(1, rms * 3);
}

/**
 * Convert Float32Array to Int16Array (PCM)
 */
function floatTo16BitPCM(float32Array: Float32Array): Int16Array {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16Array;
}

/**
 * Resample audio data to target sample rate
 */
function resample(
  inputData: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number
): Float32Array {
  if (inputSampleRate === outputSampleRate) {
    return inputData;
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.round(inputData.length / ratio);
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const srcIndex = i * ratio;
    const srcIndexFloor = Math.floor(srcIndex);
    const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
    const fraction = srcIndex - srcIndexFloor;

    // Linear interpolation
    output[i] = inputData[srcIndexFloor] * (1 - fraction) + inputData[srcIndexCeil] * fraction;
  }

  return output;
}

/**
 * Create audio capture instance
 */
export function createAudioCapture(options: AudioCaptureOptions): AudioCapture {
  const { mode, onAudioData, onMicLevel, onSystemLevel, onError } = options;

  let audioContext: AudioContext | null = null;
  let micStream: MediaStream | null = null;
  let systemStream: MediaStream | null = null;
  let micSource: MediaStreamAudioSourceNode | null = null;
  let systemSource: MediaStreamAudioSourceNode | null = null;
  let processor: ScriptProcessorNode | null = null;
  let micAnalyser: AnalyserNode | null = null;
  let systemAnalyser: AnalyserNode | null = null;
  let levelInterval: NodeJS.Timeout | null = null;
  let isPaused = false;

  const start = async () => {
    try {
      // Create audio context
      audioContext = new AudioContext({ sampleRate: 48000 }); // Start with high quality

      // Get microphone stream
      micStream = await getMicrophoneStream();
      micSource = audioContext.createMediaStreamSource(micStream);

      // Create mic analyser for level metering
      micAnalyser = audioContext.createAnalyser();
      micAnalyser.fftSize = 256;
      micSource.connect(micAnalyser);

      // Get system audio if needed
      if (mode === 'mic-and-system') {
        try {
          systemStream = await getSystemAudioStream();
          systemSource = audioContext.createMediaStreamSource(systemStream);

          // Create system analyser for level metering
          systemAnalyser = audioContext.createAnalyser();
          systemAnalyser.fftSize = 256;
          systemSource.connect(systemAnalyser);
        } catch (err) {
          // If system audio fails, continue with mic only
          const message = err instanceof Error ? err.message : 'Failed to capture system audio';
          onError(message + ' Continuing with microphone only.');
        }
      }

      // Create gain nodes for mixing
      const micGain = audioContext.createGain();
      micGain.gain.value = 1.0;
      micSource.connect(micGain);

      let mixerNode: GainNode;

      if (systemSource) {
        const systemGain = audioContext.createGain();
        systemGain.gain.value = 1.0;
        systemSource.connect(systemGain);

        // Create mixer
        mixerNode = audioContext.createGain();
        mixerNode.gain.value = 0.5; // Reduce overall volume when mixing
        micGain.connect(mixerNode);
        systemGain.connect(mixerNode);
      } else {
        mixerNode = micGain;
      }

      // Create script processor for audio data extraction
      // TODO: Migrate to AudioWorklet when prioritized
      // ScriptProcessorNode is deprecated but still works in all modern browsers.
      // AudioWorklet is the replacement but requires:
      //   1. A separate JS file for the AudioWorkletProcessor
      //   2. Registration via audioContext.audioWorklet.addModule()
      //   3. MessagePort communication for sending audio data
      // Benefits of migration: runs on audio thread (no main thread blocking),
      // lower latency, better performance during heavy UI operations.
      // Current approach works fine for typical use cases.
      processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1);

      processor.onaudioprocess = (e) => {
        if (isPaused) return;

        const inputData = e.inputBuffer.getChannelData(0);

        // Resample to target sample rate
        const resampledData = resample(inputData, audioContext!.sampleRate, TARGET_SAMPLE_RATE);

        // Convert to PCM
        const pcmData = floatTo16BitPCM(resampledData);

        // Send to callback
        onAudioData(pcmData);
      };

      mixerNode.connect(processor);
      processor.connect(audioContext.destination);

      // Start level metering
      const micDataArray = new Float32Array(micAnalyser.fftSize);
      const systemDataArray = systemAnalyser ? new Float32Array(systemAnalyser.fftSize) : null;

      levelInterval = setInterval(() => {
        if (isPaused) return;

        // Mic level
        micAnalyser!.getFloatTimeDomainData(micDataArray);
        onMicLevel(calculateLevel(micDataArray));

        // System level
        if (systemAnalyser && systemDataArray) {
          systemAnalyser.getFloatTimeDomainData(systemDataArray);
          onSystemLevel(calculateLevel(systemDataArray));
        } else {
          onSystemLevel(0);
        }
      }, 100);
    } catch (err) {
      cleanup();
      const message = err instanceof Error ? err.message : 'Failed to start recording';
      onError(message);
      throw err;
    }
  };

  const stop = () => {
    cleanup();
  };

  const pause = () => {
    isPaused = true;
  };

  const resume = () => {
    isPaused = false;
  };

  const cleanup = () => {
    if (levelInterval) {
      clearInterval(levelInterval);
      levelInterval = null;
    }

    if (processor) {
      processor.disconnect();
      processor = null;
    }

    if (micSource) {
      micSource.disconnect();
      micSource = null;
    }

    if (systemSource) {
      systemSource.disconnect();
      systemSource = null;
    }

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
      micStream = null;
    }

    if (systemStream) {
      systemStream.getTracks().forEach((track) => track.stop());
      systemStream = null;
    }

    if (audioContext) {
      audioContext.close();
      audioContext = null;
    }

    isPaused = false;
  };

  return { start, stop, pause, resume };
}

/**
 * Check if browser supports required audio APIs
 */
export function isAudioCaptureSupported(): boolean {
  return !!(
    typeof navigator !== 'undefined' &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function'
  );
}

/**
 * Check if browser supports system audio capture
 */
export function isSystemAudioSupported(): boolean {
  return !!(
    typeof navigator !== 'undefined' &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getDisplayMedia === 'function'
  );
}

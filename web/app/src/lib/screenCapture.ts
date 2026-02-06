/**
 * Screen capture utilities for proactive notifications.
 * Handles screen sharing with video frame capture and system audio.
 */

export interface ScreenCaptureStream {
    stream: MediaStream;
    videoTrack: MediaStreamTrack;
    audioTrack: MediaStreamTrack | null;
}

export interface FrameCaptureOptions {
    intervalMs: number;
    onFrame: (jpegBlob: Blob) => void;
    onError: (error: string) => void;
}

export interface FrameCapture {
    start: () => void;
    stop: () => void;
    pause: () => void;
    resume: () => void;
    captureNow: () => Promise<Blob | null>;
}

/**
 * Request screen capture with video and optional audio
 */
export async function getScreenCaptureStream(): Promise<ScreenCaptureStream> {
    try {
        const stream = await navigator.mediaDevices.getDisplayMedia({
            video: {
                width: { ideal: 1920 },
                height: { ideal: 1080 },
                frameRate: { ideal: 1 }, // Low FPS since we only need periodic frames
            },
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
            },
        });

        const videoTracks = stream.getVideoTracks();
        if (videoTracks.length === 0) {
            stream.getTracks().forEach((track) => track.stop());
            throw new Error('No video track available. Please share a screen or window.');
        }

        const audioTracks = stream.getAudioTracks();

        return {
            stream,
            videoTrack: videoTracks[0],
            audioTrack: audioTracks.length > 0 ? audioTracks[0] : null,
        };
    } catch (err) {
        if (err instanceof DOMException) {
            if (err.name === 'NotAllowedError') {
                throw new Error('Screen share cancelled. Screen capture requires sharing a tab or window.');
            }
        }
        if (err instanceof Error) {
            throw err;
        }
        throw new Error('Failed to start screen capture');
    }
}

/**
 * Create a frame capture instance from a video track
 */
export function createFrameCapture(
    videoTrack: MediaStreamTrack,
    options: FrameCaptureOptions
): FrameCapture {
    const { intervalMs, onFrame, onError } = options;

    let captureInterval: NodeJS.Timeout | null = null;
    let startTimeout: NodeJS.Timeout | null = null;
    let isPaused = false;
    let videoElement: HTMLVideoElement | null = null;
    let canvas: HTMLCanvasElement | null = null;
    let ctx: CanvasRenderingContext2D | null = null;
    let initPromise: Promise<void> | null = null;

    function initializeCapture(): Promise<void> {
        if (initPromise) return initPromise;

        initPromise = new Promise((resolve, reject) => {
            try {
                // Create hidden video element
                videoElement = document.createElement('video');
                videoElement.srcObject = new MediaStream([videoTrack]);
                videoElement.autoplay = true;
                videoElement.muted = true;
                videoElement.playsInline = true;

                // Create canvas for frame extraction
                canvas = document.createElement('canvas');
                ctx = canvas.getContext('2d');

                if (!ctx) {
                    throw new Error('Failed to get 2D context from canvas');
                }

                // Start playing
                videoElement.play().then(() => resolve()).catch((err) => {
                    onError(`Failed to play video: ${err.message}`);
                    reject(err);
                });
            } catch (err) {
                const msg = err instanceof Error ? err.message : 'Capture initialization failed';
                onError(msg);
                reject(err);
            }
        });

        return initPromise;
    }

    async function captureFrame(): Promise<Blob | null> {
        if (!videoElement || !canvas || !ctx) {
            return null;
        }

        // Wait for video to have dimensions
        if (videoElement.videoWidth === 0 || videoElement.videoHeight === 0) {
            return null;
        }

        // Set canvas size to match video
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;

        // Draw current frame
        ctx.drawImage(videoElement, 0, 0);

        // Convert to JPEG blob
        return new Promise((resolve) => {
            canvas!.toBlob(
                (blob) => {
                    resolve(blob);
                },
                'image/jpeg',
                0.8 // Quality setting for smaller file size
            );
        });
    }

    async function captureAndSend(): Promise<void> {
        if (isPaused) return;

        try {
            const blob = await captureFrame();
            if (blob) {
                onFrame(blob);
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to capture frame';
            onError(message);
        }
    }

    function start(): void {
        if (!videoElement) {
            initializeCapture();
        }

        // Capture first frame after a short delay (let video initialize)
        startTimeout = setTimeout(() => {
            captureAndSend();
            startTimeout = null;
        }, 500);

        // Start interval
        captureInterval = setInterval(captureAndSend, intervalMs);
    }

    function stop(): void {
        if (captureInterval) {
            clearInterval(captureInterval);
            captureInterval = null;
        }

        if (startTimeout) {
            clearTimeout(startTimeout);
            startTimeout = null;
        }

        if (videoElement) {
            videoElement.srcObject = null;
            videoElement = null;
        }

        canvas = null;
        ctx = null;
        initPromise = null;
        isPaused = false;
    }

    function pause(): void {
        isPaused = true;
    }

    function resume(): void {
        isPaused = false;
    }

    async function captureNow(): Promise<Blob | null> {
        if (!videoElement) {
            await initializeCapture();
            // Wait for video to initialize
            // Re-check videoElement as initializeCapture is side-effectual
            if (videoElement && (videoElement.readyState < 2)) {
                await new Promise((resolve) => setTimeout(resolve, 500));
            }
        }
        return captureFrame();
    }

    return { start, stop, pause, resume, captureNow };
}

/**
 * Check if browser supports screen capture
 */
export function isScreenCaptureSupported(): boolean {
    return !!(
        typeof navigator !== 'undefined' &&
        navigator.mediaDevices &&
        typeof navigator.mediaDevices.getDisplayMedia === 'function'
    );
}

/**
 * Stop all tracks in a screen capture stream
 */
export function stopScreenCapture(capture: ScreenCaptureStream): void {
    capture.stream.getTracks().forEach((track) => track.stop());
}

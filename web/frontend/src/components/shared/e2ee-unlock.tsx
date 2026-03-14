'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { storeKey, importKey, computeKeyHash, storeKeyHash } from '@/src/lib/e2ee';

interface E2eeUnlockProps {
  onUnlocked: () => void;
  onClose: () => void;
}

export default function E2eeUnlock({ onUnlocked, onClose }: E2eeUnlockProps) {
  const [mode, setMode] = useState<'scan' | 'paste'>('scan');
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState(false);
  const [pasteValue, setPasteValue] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scannerRef = useRef<number | null>(null);

  const handleKey = useCallback(
    async (base64Key: string) => {
      try {
        await importKey(base64Key); // Validate
        await storeKey(base64Key);
        const hash = await computeKeyHash(base64Key);
        storeKeyHash(hash);
        setSuccess(true);
        setTimeout(() => {
          onUnlocked();
        }, 1500);
      } catch {
        setError('Invalid key. Please try again.');
      }
    },
    [onUnlocked],
  );

  const stopScanning = useCallback(() => {
    if (scannerRef.current) {
      cancelAnimationFrame(scannerRef.current);
      scannerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const startScanning = useCallback(async () => {
    try {
      // Check if BarcodeDetector is available
      if (!('BarcodeDetector' in window)) {
        setError(
          'QR scanning not supported in this browser. Please paste your recovery key instead.',
        );
        setMode('paste');
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detector = new (window as unknown as Record<string, any>).BarcodeDetector({
        formats: ['qr_code'],
      });

      const scan = async () => {
        if (!videoRef.current || !streamRef.current) return;
        try {
          const barcodes = await detector.detect(videoRef.current);
          for (const barcode of barcodes) {
            try {
              const data = JSON.parse(barcode.rawValue);
              if (data.type === 'omi_e2ee_key' && data.key) {
                stopScanning();
                await handleKey(data.key);
                return;
              }
            } catch {
              // Ignore non-JSON QR codes
            }
          }
        } catch {
          // Detection error, continue scanning
        }
        scannerRef.current = requestAnimationFrame(scan);
      };

      scannerRef.current = requestAnimationFrame(scan);
    } catch {
      setError('Camera access denied. Please paste your recovery key instead.');
      setMode('paste');
    }
  }, [handleKey, stopScanning]);

  useEffect(() => {
    if (mode === 'scan') {
      startScanning();
    }
    return () => stopScanning();
  }, [mode, startScanning, stopScanning]);

  const handlePaste = async () => {
    if (!pasteValue.trim()) return;
    await handleKey(pasteValue.trim());
  };

  if (success) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
        <div className="mx-4 w-full max-w-md rounded-2xl bg-zinc-900 p-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-500/20">
            <svg
              className="h-8 w-8 text-green-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-white">Unlocked</h3>
          <p className="mt-2 text-zinc-400">Your encrypted data is now accessible</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="mx-4 w-full max-w-md rounded-2xl bg-zinc-900 p-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg
              className="h-5 w-5 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            <h3 className="text-lg font-bold text-white">Unlock Encrypted Data</h3>
          </div>
          <button
            onClick={() => {
              stopScanning();
              onClose();
            }}
            className="text-zinc-500 hover:text-white"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Mode tabs */}
        <div className="mb-4 flex rounded-lg bg-zinc-800 p-1">
          <button
            onClick={() => setMode('scan')}
            className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
              mode === 'scan'
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            📷 Scan QR
          </button>
          <button
            onClick={() => {
              stopScanning();
              setMode('paste');
            }}
            className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
              mode === 'paste'
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            📋 Paste Key
          </button>
        </div>

        {mode === 'scan' ? (
          <div>
            <div className="relative overflow-hidden rounded-xl bg-black">
              <video
                ref={videoRef}
                className="h-64 w-full object-cover"
                playsInline
                muted
              />
              {/* Scanning overlay */}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="h-48 w-48 rounded-2xl border-2 border-white/30" />
              </div>
            </div>
            <p className="mt-3 text-center text-sm text-zinc-500">
              Open Omi app → Settings → Data Privacy → Pair with Web
            </p>
          </div>
        ) : (
          <div>
            <p className="mb-3 text-sm text-zinc-400">
              Paste your recovery key from the Omi app
            </p>
            <input
              type="password"
              value={pasteValue}
              onChange={(e) => {
                setPasteValue(e.target.value);
                setError('');
              }}
              placeholder="Paste recovery key..."
              className="w-full rounded-lg bg-zinc-800 px-4 py-3 text-white placeholder-zinc-600 outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              onClick={handlePaste}
              disabled={!pasteValue.trim()}
              className="mt-3 w-full rounded-lg bg-purple-600 py-3 font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
            >
              Unlock
            </button>
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-lg bg-red-500/10 px-4 py-2 text-sm text-red-400">
            {error}
          </div>
        )}

        <p className="mt-4 text-center text-xs text-zinc-600">
          Your key stays in this browser tab and is never sent to the server
        </p>
      </div>
    </div>
  );
}

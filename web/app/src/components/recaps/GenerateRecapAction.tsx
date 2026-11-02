'use client';

import { useEffect, useRef, useState } from 'react';
import { CalendarPlus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { recapGenerationError } from '@/lib/recapGeneration';
import type { DailySummary } from '@/types/recap';

function dateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
    date.getDate(),
  ).padStart(2, '0')}`;
}

export function GenerateRecapAction({
  generate,
  onCreated,
}: {
  generate: (date: string) => Promise<DailySummary>;
  onCreated: (recap: DailySummary) => void;
}) {
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  const oldest = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(dateKey(yesterday));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const opened = useRef(open);
  opened.current = open;
  const pending = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      const recap = await generate(date);
      if (!alive.current) return;
      if (opened.current) {
        onCreated(recap);
        setOpen(false);
      }
    } catch (error) {
      if (alive.current) setError(recapGenerationError(error));
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        {busy ? (
          <Loader2 className="mr-2 h-4 w-4 motion-safe:animate-spin" aria-hidden />
        ) : (
          <CalendarPlus className="mr-2 h-4 w-4" aria-hidden />
        )}
        {busy ? 'Generating recap…' : 'Generate recap'}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate a daily recap</DialogTitle>
            <DialogDescription>
              Recover a missing day from conversations already saved for that day.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-5">
            <div className="space-y-2">
              <label
                htmlFor="recap-generation-date"
                className="text-sm text-text-secondary"
              >
                Date
              </label>
              <input
                id="recap-generation-date"
                type="date"
                required
                min={dateKey(oldest)}
                max={dateKey(today)}
                value={date}
                disabled={busy}
                onChange={(event) => setDate(event.target.value)}
                className="block w-full rounded-control border border-stroke bg-bg-primary px-3 py-2.5 text-base text-text-primary [color-scheme:dark] focus:outline-none focus:ring-1 focus:ring-white/40"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-text-primary">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                {busy ? 'Close' : 'Cancel'}
              </Button>
              <Button type="submit" disabled={busy || !date}>
                {busy ? (
                  <>
                    <Loader2
                      className="mr-2 h-4 w-4 motion-safe:animate-spin"
                      aria-hidden
                    />
                    Generating…
                  </>
                ) : (
                  'Generate recap'
                )}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

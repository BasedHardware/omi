/**
 * Backpressure-aware JSONL line sender for the agent→parent stdout pipe.
 *
 * Synchronous `process.stdout.write` can block the Node event loop when the
 * parent stops draining (full pipe). Queue lines and wait for `drain` instead
 * of stalling kernel/event subscribers mid-turn.
 */

export type StdoutWrite = (chunk: string) => boolean;
export type StdoutOnDrain = (listener: () => void) => void;
export type StdoutWriteError = (error: unknown) => void;

export function createStdoutLineSender(
  write: StdoutWrite,
  onDrain: StdoutOnDrain,
  onWriteError: StdoutWriteError = () => {}
): (line: string) => void {
  const queue: string[] = [];
  let waitingForDrain = false;

  const pump = (): void => {
    if (waitingForDrain) return;
    while (queue.length > 0) {
      const line = queue[0]!;
      let ok = true;
      try {
        ok = write(line);
      } catch (error) {
        onWriteError(error);
        queue.shift();
        continue;
      }
      queue.shift();
      if (!ok) {
        waitingForDrain = true;
        onDrain(() => {
          waitingForDrain = false;
          pump();
        });
        return;
      }
    }
  };

  return (line: string): void => {
    queue.push(line);
    pump();
  };
}

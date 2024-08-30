import { TranscriptSegment } from '@/src/types/memory.types';
import TranscriptionSegment from './transcription-segment';
import { Fragment } from 'react';

interface TranscriptionProps {
  transcript: TranscriptSegment[];
}

export default function Transcription({ transcript }: TranscriptionProps) {
  const uniqueSpeakers = Array.from(
    new Set(transcript.map((segment) => segment.speaker_id)),
  );
  return (
    <div>
      <h3 className="mt-10 text-xl font-semibold md:text-2xl">Transcription</h3>
      {transcript.length === 0 ? (
        <p className="mt-4 text-gray-400">
          There is no transcription available for this memory.
        </p>
      ) : (
        <Fragment>
          <span className="text-sm font-light text-gray-400 md:text-base">
            Total Speakers: {uniqueSpeakers.length}
          </span>
          <ul className="mt-4">
            {transcript.map((segment, index) => (
              <TranscriptionSegment key={index} segment={segment} />
            ))}
          </ul>
        </Fragment>
      )}
    </div>
  );
}

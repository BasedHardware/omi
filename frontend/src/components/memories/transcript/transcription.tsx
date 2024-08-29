import { TranscriptSegment } from '@/src/types/memory.types';
import TranscriptionSegment from './transcription-segment';

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
      <span className="text-sm font-light text-gray-400 md:text-base">
        Total Speakers: {uniqueSpeakers.length}
      </span>
      <ul className="mt-4">
        {transcript.map((segment, index) => (
          <TranscriptionSegment key={index} segment={segment} />
        ))}
      </ul>
    </div>
  );
}

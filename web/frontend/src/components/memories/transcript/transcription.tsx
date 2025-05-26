import {
  ExternalData as ExternalDataType,
  TranscriptSegment,
} from '@/src/types/memory.types';
import TranscriptionSegment from './transcription-segment';
import ExternalData from '../external-data/external-data';

interface TranscriptionProps {
  transcript: TranscriptSegment[];
  externalData: ExternalDataType | null;
}

export default function Transcription({ transcript, externalData }: TranscriptionProps) {
  if (transcript.length === 0 && externalData) {
    return <ExternalData externalData={externalData} />;
  } else if (transcript.length === 0 && !externalData) {
    return (
      <div className="px-4 md:px-12">
        <h3 className="mt-10 text-xl font-semibold md:text-2xl">Transcription</h3>
        <p className="mt-4 text-gray-400">No available data.</p>
      </div>
    );
  } else {
    const uniqueSpeakers = Array.from(
      new Set(transcript.map((segment) => segment.speaker_id)),
    );
    return (
      <div className="px-4 md:px-12">
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
}

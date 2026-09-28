import {
  ExternalData as ExternalDataType,
  TranscriptSegment,
  Person,
} from '@/src/types/memory.types';
import TranscriptionSegment from './transcription-segment';
import ExternalData from '../external-data/external-data';

interface TranscriptionProps {
  transcript: TranscriptSegment[];
  externalData: ExternalDataType | null;
  people?: Person[];
}

export default function Transcription({
  transcript,
  externalData,
  people,
}: TranscriptionProps) {
  if (transcript.length === 0 && externalData) {
    return <ExternalData externalData={externalData} />;
  } else if (transcript.length === 0 && !externalData) {
    return (
      <div>
        <h2 className="sn-h3 mt-10">Transcript</h2>
        <p className="sn-muted mt-4">No available data.</p>
      </div>
    );
  } else {
    const uniqueSpeakers = Array.from(
      new Set(transcript.map((segment) => segment.speaker_id)),
    );
    return (
      <div>
        <h2 className="sn-h3 mt-10">Transcript</h2>
        <span className="sn-muted text-sm md:text-base">
          {uniqueSpeakers.length} {uniqueSpeakers.length === 1 ? 'speaker' : 'speakers'}
        </span>
        <ul className="sn-transcript">
          {transcript.map((segment, index) => (
            <TranscriptionSegment key={index} segment={segment} people={people} />
          ))}
        </ul>
      </div>
    );
  }
}

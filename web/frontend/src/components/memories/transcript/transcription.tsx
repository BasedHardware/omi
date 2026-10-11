import {
  ExternalData as ExternalDataType,
  TranscriptSegment,
  Person,
  Participant,
} from '@/src/types/memory.types';
import { transcriptSpeakerResolver } from '@/src/lib/shared-note.mjs';
import TranscriptionSegment from './transcription-segment';
import ExternalData from '../external-data/external-data';

interface TranscriptionProps {
  transcript: TranscriptSegment[];
  externalData: ExternalDataType | null;
  people?: Person[];
  participants?: Participant[] | null;
}

export default function Transcription({
  transcript,
  externalData,
  people,
  participants,
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
    const resolveSpeaker = transcriptSpeakerResolver(people, participants, transcript);
    return (
      <div>
        <h2 className="sn-h3 mt-10">Transcript</h2>
        <span className="sn-muted text-sm md:text-base">
          Offsets from conversation start (HH:MM:SS) · {uniqueSpeakers.length}{' '}
          {uniqueSpeakers.length === 1 ? 'speaker' : 'speakers'}
        </span>
        <ul className="sn-transcript">
          {transcript.map((segment, index) => (
            <TranscriptionSegment
              key={index}
              segment={segment}
              displayName={resolveSpeaker(segment)}
            />
          ))}
        </ul>
      </div>
    );
  }
}

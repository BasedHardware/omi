import { TranscriptSegment } from '@/src/types/memory.types';
import { UserCircle } from 'iconoir-react';

interface TranscriptionProps {
  transcript: TranscriptSegment[];
}

export default function Transcription({ transcript }: TranscriptionProps) {
  return (
    <div>
      <h3 className="text-2xl font-semibold mt-10">Transcription</h3>
      <ul className="mt-3">
        {transcript.map((segment, index) => (
          <li key={segment.speaker_id} className="my-5 flex gap-2">
            <UserCircle className="min-w-min text-sm mt-1" />
            <div>
              <p className='text-lg font-semibold'>Speaker {segment.speaker_id}</p>
              <p className='font-light'>{segment.text.replace(`Speaker ${index}:`, '').charAt(0).toUpperCase() + segment.text.replace(`Speaker ${index}:`, '').slice(1)}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

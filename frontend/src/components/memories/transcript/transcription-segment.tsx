import { predefinedColors } from '@/src/constants/colors';
import { TranscriptSegment } from '@/src/types/memory.types';
import { UserCircle } from 'iconoir-react';

export default function TranscriptionSegment({
  segment,
}: {
  segment: TranscriptSegment;
}) {
  const color = predefinedColors[segment.speaker_id % predefinedColors.length];

  return (
    <li className="my-5 flex gap-2">
      <UserCircle className="mt-1 min-w-min text-sm" color={color} />
      <div>
        <p className="text-lg font-semibold">Speaker {segment.speaker_id}</p>
        <p className="font-extralight">
          {segment.text
            .replace(`Speaker ${segment.speaker_id}:`, '')
            .charAt(0)
            .toUpperCase() +
            segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1)}
        </p>
      </div>
    </li>
  );
}

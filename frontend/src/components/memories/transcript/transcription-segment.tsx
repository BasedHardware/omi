'use client';

import { predefinedColors } from '@/src/constants/colors';
import { TranscriptSegment } from '@/src/types/memory.types';
import { UserCircle } from 'iconoir-react';
import { useState } from 'react';

export default function TranscriptionSegment({
  segment,
}: {
  segment: TranscriptSegment;
}) {
  const color = predefinedColors[segment.speaker_id % predefinedColors.length];
  const [showMore, setShowMore] = useState(false);

  const textFormatted = segment.text
    .replace(`Speaker ${segment.speaker_id}:`, '')
    .charAt(0)
    .toUpperCase() + segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1)

  return (
    <li className="my-5 flex gap-2">
      <UserCircle className="mt-1 min-w-min text-sm" color={color} />
      <div>
        <p className="text-base md:text-lg font-semibold">Speaker {segment.speaker_id}</p>
        <p className="font-extralight text-base md:text-lg leading-7 md:leading-9">
          {showMore
            ? textFormatted
            : textFormatted.slice(0, 600) + (textFormatted.length > 600 ? '...' : '')}{" "}
          {segment.text.length > 600 && (
            <button onClick={() => setShowMore(!showMore)} className="text-blue-500 inline hover:underline">
             {showMore ? ' Show less' : ' Show more'}
            </button>
          )}
        </p>
      </div>
    </li>
  );
}

import { TranscriptSegment } from "@/src/types/memory.types";

interface TranscriptionProps {
  transcript: TranscriptSegment[];
}

export default function Transcription({ transcript }: TranscriptionProps){
  return (
    <div>
      <h3 className="text-2xl font-semibold">Transcription</h3>
      <ul className="mt-3">
        {transcript.map((segment, index) => (
          <li key={index} className="my-2">
            <p>
              {segment.text}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}
"""Test script to verify audio chunking works"""
import asyncio
from app import analyze_audio_with_hume
import sys

async def test_audio_file(file_path):
    print(f"\n{'='*60}")
    print(f"Testing: {file_path}")
    print(f"{'='*60}\n")

    result = await analyze_audio_with_hume(file_path)

    print(f"\n{'='*60}")
    print("RESULT:")
    print(f"{'='*60}")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"Chunked: {result.get('chunked', False)}")
        if result.get('chunked'):
            print(f"Number of chunks: {result.get('num_chunks')}")
            print(f"Total duration: {result.get('total_duration_seconds'):.2f}s")
        print(f"Total predictions: {result.get('total_predictions')}")

        if result.get('predictions'):
            print(f"\nFirst prediction:")
            pred = result['predictions'][0]
            print(f"  Time: {pred['time']['begin']:.2f}s - {pred['time']['end']:.2f}s")
            if 'chunk_index' in pred:
                print(f"  Chunk: {pred['chunk_index']}")
            print(f"  Top 3 emotions:")
            for emotion in pred['top_3_emotions']:
                print(f"    - {emotion['name']}: {emotion['score']:.3f}")
    else:
        print(f"Error: {result.get('error')}")
        if 'debug_info' in result:
            print(f"Debug info: {result['debug_info']}")

    print(f"\n{'='*60}\n")
    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        # Use most recent file
        import glob
        files = sorted(glob.glob("audio_files/*.wav"))
        if not files:
            print("No audio files found in audio_files/")
            sys.exit(1)
        file_path = files[-1]

    asyncio.run(test_audio_file(file_path))

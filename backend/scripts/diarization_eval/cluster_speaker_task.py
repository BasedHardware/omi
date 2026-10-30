#!/usr/bin/env python3
"""Local pinned WeSpeaker embeddings and AHC-0.5 review groups, never identities."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from .prep_speaker_task import private_dir, write_private
else:
    from prep_speaker_task import private_dir, write_private

MODEL = 'pyannote/wespeaker-voxceleb-resnet34-LM'
REVISION = '837717ddb9ff5507820346191109dc79c958d614'


def ahc_groups(vectors, threshold=0.5):
    """Average-linkage cosine clustering; labels only organize human review."""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    if not vectors:
        return []
    array = np.asarray(vectors, dtype=float)
    if array.ndim != 2 or not np.isfinite(array).all() or (np.linalg.norm(array, axis=1) == 0).any():
        raise ValueError('invalid review embeddings')
    if len(array) == 1:
        return [0]
    return (
        fcluster(linkage(pdist(array, metric='cosine'), method='average'), t=threshold, criterion='distance') - 1
    ).tolist()


def local_embed(media, start, end, scratch):
    """Extract bounded local audio; no network embedding endpoint or enrollment."""
    import numpy as np
    import torch
    from diarizer.embedding import embedding_inference_v2

    clip = Path(scratch) / 'clip.wav'
    subprocess.run(
        [
            'ffmpeg',
            '-nostdin',
            '-v',
            'error',
            '-y',
            '-ss',
            str(start),
            '-i',
            str(media),
            '-t',
            str(end - start),
            '-ar',
            '16000',
            '-ac',
            '1',
            '-c:a',
            'pcm_s16le',
            str(clip),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    clip.chmod(0o600)
    import wave

    with wave.open(str(clip), 'rb') as stream:
        pcm = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32) / 32768
    return (
        np.asarray(embedding_inference_v2({'waveform': torch.from_numpy(pcm).unsqueeze(0), 'sample_rate': 16000}))
        .reshape(-1)
        .tolist()
    )


def cluster(reference, output, *, embed=None):
    reference = json.loads(Path(reference).read_text()) if isinstance(reference, (str, Path)) else reference
    private_dir(Path(output).parent)
    embed = embed or local_embed
    results = []
    with tempfile.TemporaryDirectory(dir=Path(output).parent) as scratch:
        for recording in reference['recordings']:
            vectors, eligible = [], []
            for index, segment in enumerate(recording['segments']):
                if segment['end'] - segment['start'] < 0.5:
                    continue
                vectors.append(embed(recording['media'], segment['start'], segment['end'], scratch))
                eligible.append(index)
            assignments = ahc_groups(vectors)
            groups = []
            for index, assignment, vector in zip(eligible, assignments, vectors):
                groups.append({'segment_index': index, 'review_group': f"review-{assignment}", 'embedding': vector})
            results.append({'id': recording['id'], 'segments': groups})
    artifact = {
        'schema_version': 1,
        'purpose': 'human_review_only',
        'automatic_identity': False,
        'model': MODEL,
        'revision': REVISION,
        'method': 'average_linkage_cosine',
        'threshold': 0.5,
        'recordings': results,
    }
    write_private(output, artifact)
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = cluster(args.reference, args.output)
    except Exception:
        parser.exit(1, 'BLOCKED: local review grouping failed; inspect private inputs locally\n')
    print(
        json.dumps(
            {
                'recordings': len(result['recordings']),
                'review_clips': sum(len(r['segments']) for r in result['recordings']),
            }
        )
    )


if __name__ == '__main__':
    main()

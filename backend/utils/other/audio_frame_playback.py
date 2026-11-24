"""One bounded object download serves all its separately timed playback spans."""

from utils.other.raw_audio_read import select_raw_pcm


def group_frame_jobs(timestamps, by_timestamp):
    individual = []
    grouped = {}
    for timestamp in timestamps:
        entry = by_timestamp.get(timestamp)
        if entry is None:
            individual.append(timestamp)
        else:
            grouped.setdefault(entry['path'], []).append(entry)
    return individual, grouped


def read_frame_fragments(path, frames, sample_rate, loader):
    pcm = loader(path)
    if pcm is None:
        return None
    return {entry['timestamp']: select_raw_pcm(pcm, entry, sample_rate) for entry in frames}

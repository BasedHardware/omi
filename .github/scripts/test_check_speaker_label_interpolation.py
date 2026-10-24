import unittest

from check_speaker_label_interpolation import regressions


class SpeakerPresentationRatchetTest(unittest.TestCase):
    def test_python_interpolations(self):
        for source in [
            'x = f"Speaker {segment.speaker_id}"',
            'x = f"{speaker_id}: hello"',
            'x = "Speaker {}".format(segment["speaker_id"])',
            'x = "Speaker %s" % raw_speaker_id',
            'x = f"Speaker {speaker}"',
            'x = "Speaker " + value',
            'x = f"Speaker {display_key}"',
            'sid = segment.speaker_id\nx = f"Who: {sid}"',
            'x = f"{segment.speaker}"',
            'x = "Speaker {speaker_id}".format(**segment)',
            'x = "Speaker %(speaker_id)s" % segment',
        ]:
            with self.subTest(source=source):
                self.assertTrue(regressions('backend/utils/review.py', '', source))

    def test_baseline_is_fingerprinted(self):
        old = 'x = f"Speaker {speaker_id}"'
        self.assertFalse(regressions('backend/utils/review.py', old, old))
        self.assertFalse(regressions('backend/utils/review.py', old, 'x = names.label(row)'))
        self.assertTrue(regressions('backend/utils/review.py', old, 'x = f"Who: {speaker_id}"'))

    def test_authority_and_tests(self):
        for path in ['backend/utils/speakers/display.py', 'backend/tests/unit/test_display.py']:
            self.assertFalse(regressions(path, '', 'x = f"{speaker_id}"'))

    def test_dart(self):
        self.assertTrue(
            regressions('backend/utils/new_renderer.py', '', 'from utils.speaker_display import SpeakerLabeler')
        )
        self.assertFalse(
            regressions('backend/utils/new_renderer.py', '', 'from utils.speakers.display import display_participants')
        )
        self.assertTrue(regressions('app/lib/widgets/transcript.dart', '', 'Text("Speaker ${segment.speakerId}")'))
        self.assertFalse(regressions('app/lib/widgets/transcript.dart', '', 'Text(names.forSegment(segment))'))


if __name__ == '__main__':
    unittest.main()

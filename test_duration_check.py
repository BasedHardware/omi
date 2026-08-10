import sys
import unittest
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.append('backend')

import utils.conversations.postprocess_conversation as ppc
from models.conversation_enums import PostProcessingStatus

class TestPostprocessDuration(unittest.TestCase):
    @patch('utils.conversations.postprocess_conversation.AudioSegment.from_wav')
    @patch('utils.conversations.postprocess_conversation._get_conversation_by_id')
    @patch('utils.conversations.postprocess_conversation.deserialize_conversation')
    @patch('utils.conversations.postprocess_conversation.conversations_db.set_postprocessing_status')
    def test_duration_too_short(self, mock_set_status, mock_deserialize, mock_get_conv, mock_from_wav):
        mock_conv_data = {'id': 'test_id'}
        mock_get_conv.return_value = mock_conv_data

        mock_conv = MagicMock()
        mock_conv.id = 'test_id'
        mock_conv.discarded = False
        mock_conv.postprocessing = None

        seg1 = MagicMock()
        seg1.start = 5
        seg2 = MagicMock()
        seg2.end = 45
        mock_conv.transcript_segments = [seg1, seg2]
        mock_deserialize.return_value = mock_conv

        mock_aseg = MagicMock()
        mock_aseg.duration_seconds = 20
        mock_from_wav.return_value = mock_aseg

        status, msg = ppc.postprocess_conversation(
            'test_id', 'test_path', 'test_uid', False, 'test_model'
        )

        self.assertEqual(status, 500)
        self.assertEqual(msg, "Audio duration is too short, seems wrong.")
        mock_set_status.assert_called_with('test_uid', 'test_id', PostProcessingStatus.canceled)

    @patch('utils.conversations.postprocess_conversation.AudioSegment.from_wav')
    @patch('utils.conversations.postprocess_conversation._get_conversation_by_id')
    @patch('utils.conversations.postprocess_conversation.deserialize_conversation')
    @patch('utils.conversations.postprocess_conversation.conversations_db.set_postprocessing_status')
    @patch('utils.conversations.postprocess_conversation.vad_is_empty')
    def test_duration_ok_calls_next_steps(self, mock_vad, mock_set_status, mock_deserialize, mock_get_conv, mock_from_wav):
        mock_conv_data = {'id': 'test_id'}
        mock_get_conv.return_value = mock_conv_data

        mock_conv = MagicMock()
        mock_conv.id = 'test_id'
        mock_conv.discarded = False
        mock_conv.postprocessing = None

        seg1 = MagicMock()
        seg1.start = 5
        seg2 = MagicMock()
        seg2.end = 45
        mock_conv.transcript_segments = [seg1, seg2]
        mock_deserialize.return_value = mock_conv

        mock_aseg = MagicMock()
        mock_aseg.duration_seconds = 40 # > 30 so ok
        mock_from_wav.return_value = mock_aseg

        mock_vad.side_effect = Exception("Stop early") # Stop execution early but after duration check

        status, msg = ppc.postprocess_conversation(
            'test_id', 'test_path', 'test_uid', False, 'test_model'
        )

        # the function should fail later but we assert that set_postprocessing_status was called with in_progress
        # before the exception (meaning it passed the check)
        mock_set_status.assert_any_call('test_uid', 'test_id', PostProcessingStatus.in_progress)

if __name__ == '__main__':
    unittest.main()

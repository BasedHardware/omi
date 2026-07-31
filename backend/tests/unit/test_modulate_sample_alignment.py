"""Velma streaming frames must be a whole number of 16-bit samples.

Verified against the live API: a frame whose byte count is odd is answered with
{"type":"error","error":"Invalid input audio"} (5/5 trials) and the provider then
closes the socket, so one misaligned frame ends the session even when it arrives
after valid audio. Nothing upstream of this socket guarantees even-length buffers —
``flush_live_stt_buffer`` forwards whatever the buffer accumulated, including on the
forced teardown flush.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from utils.stt.streaming import SafeModulateSocket


class TestModulateSampleAlignment(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.ws = AsyncMock()
        self.ws.__aiter__ = AsyncMock(return_value=iter([]))

    def tearDown(self):
        self.loop.close()

    def _socket(self):
        async def create():
            sock = SafeModulateSocket(self.ws, MagicMock(), self.loop)
            sock._recv_task.cancel()
            sock._send_task.cancel()
            return sock

        return self.loop.run_until_complete(create())

    def _queued(self, sock):
        frames = []
        while not sock._send_queue.empty():
            frames.append(sock._send_queue.get_nowait())
        return frames

    def test_an_even_frame_is_forwarded_unchanged(self):
        sock = self._socket()
        audio = bytes(range(100))

        self.assertTrue(sock.send(audio))

        self.assertEqual(self._queued(sock), [audio])
        self.assertEqual(sock._pending_odd_byte, b'')

    def test_an_odd_frame_is_trimmed_and_its_tail_carried(self):
        sock = self._socket()

        self.assertTrue(sock.send(b'\x01\x02\x03'))

        self.assertEqual(self._queued(sock), [b'\x01\x02'])
        self.assertEqual(sock._pending_odd_byte, b'\x03')

    def test_the_carried_byte_leads_the_next_frame_without_loss(self):
        sock = self._socket()
        sock.send(b'\x01\x02\x03')
        self._queued(sock)

        sock.send(b'\x04\x05')

        # Sample order is preserved across the boundary: 03 04 then 05 carried.
        self.assertEqual(self._queued(sock), [b'\x03\x04'])
        self.assertEqual(sock._pending_odd_byte, b'\x05')

    def test_a_lone_odd_byte_is_buffered_and_still_reported_accepted(self):
        sock = self._socket()

        self.assertTrue(sock.send(b'\x07'))

        self.assertEqual(self._queued(sock), [])
        self.assertEqual(sock._pending_odd_byte, b'\x07')
        self.assertFalse(sock.is_connection_dead)

    def test_no_odd_frame_survives_a_run_of_odd_length_sends(self):
        sock = self._socket()

        for size in (99, 1, 3, 4097, 7, 100):
            sock.send(b'\x00' * size)

        frames = self._queued(sock)
        self.assertTrue(frames, 'expected audio to reach the provider queue')
        self.assertEqual([len(f) % 2 for f in frames], [0] * len(frames))

    def test_every_byte_reaches_the_provider_apart_from_a_trailing_carry(self):
        sock = self._socket()
        sent = [b'\x01\x02\x03', b'\x04', b'\x05\x06\x07\x08', b'\x09']

        for frame in sent:
            sock.send(frame)

        forwarded = b''.join(self._queued(sock))
        self.assertEqual(forwarded + sock._pending_odd_byte, b''.join(sent))

    def test_alignment_state_does_not_resurrect_a_dead_socket(self):
        sock = self._socket()
        sock._mark_dead('provider closed')

        self.assertFalse(sock.send(b'\x01\x02\x03'))
        self.assertEqual(self._queued(sock), [])


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,too-few-public-methods
#

"""
CTypes mapping between libopus functions and Python.
"""

import array
import ctypes  # type: ignore
import typing

import opuslib
import opuslib.api

__author__ = 'Никита Кузнецов <self@svartalf.info>'
__copyright__ = 'Copyright (c) 2012, SvartalF'
__license__ = 'BSD 3-Clause License'


class Decoder(ctypes.Structure):
    """Opus decoder state.
    This contains the complete state of an Opus decoder.
    """
    pass


DecoderPointer = ctypes.POINTER(Decoder)


libopus_get_size = opuslib.api.libopus.opus_decoder_get_size
libopus_get_size.argtypes = (ctypes.c_int,)
libopus_get_size.restype = ctypes.c_int
libopus_get_size.__doc__ = 'Gets the size of an OpusDecoder structure'


libopus_create = opuslib.api.libopus.opus_decoder_create
libopus_create.argtypes = (
    ctypes.c_int,
    ctypes.c_int,
    opuslib.api.c_int_pointer
)
libopus_create.restype = DecoderPointer


def create_state(fs: int, channels: int) -> ctypes.Structure:
    """
    Allocates and initializes a decoder state.
    Wrapper for C opus_decoder_create()

    `fs` must be one of 8000, 12000, 16000, 24000, or 48000.

    Internally Opus stores data at 48000 Hz, so that should be the default
    value for Fs. However, the decoder can efficiently decode to buffers
    at 8, 12, 16, and 24 kHz so if for some reason the caller cannot use data
    at the full sample rate, or knows the compressed data doesn't use the full
    frequency range, it can request decoding at a reduced rate. Likewise, the
    decoder is capable of filling in either mono or interleaved stereo pcm
    buffers, at the caller's request.

    :param fs: Sample rate to decode at (Hz).
    :param int: Number of channels (1 or 2) to decode.
    """
    result_code = ctypes.c_int()

    decoder_state = libopus_create(
        fs,
        channels,
        ctypes.byref(result_code)
    )

    if result_code.value is not 0:
        raise opuslib.exceptions.OpusError(result_code.value)

    return decoder_state


libopus_packet_get_bandwidth = opuslib.api.libopus.opus_packet_get_bandwidth
# `argtypes` must be a sequence (,) of types!
libopus_packet_get_bandwidth.argtypes = (ctypes.c_char_p,)
libopus_packet_get_bandwidth.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def packet_get_bandwidth(data: bytes) -> typing.Union[int, typing.Any]:
    """Gets the bandwidth of an Opus packet."""
    data_pointer = ctypes.c_char_p(data)

    result = libopus_packet_get_bandwidth(data_pointer)

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return result


libopus_packet_get_nb_channels = opuslib.api.libopus.opus_packet_get_nb_channels  # NOQA
# `argtypes` must be a sequence (,) of types!
libopus_packet_get_nb_channels.argtypes = (ctypes.c_char_p,)
libopus_packet_get_nb_channels.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def packet_get_nb_channels(data: bytes) -> typing.Union[int, typing.Any]:
    """Gets the number of channels from an Opus packet"""
    data_pointer = ctypes.c_char_p(data)

    result = libopus_packet_get_nb_channels(data_pointer)

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return result


libopus_packet_get_nb_frames = opuslib.api.libopus.opus_packet_get_nb_frames
libopus_packet_get_nb_frames.argtypes = (ctypes.c_char_p, ctypes.c_int)
libopus_packet_get_nb_frames.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def packet_get_nb_frames(
        data: bytes,
        length: typing.Optional[int] = None
) -> typing.Union[int, typing.Any]:
    """Gets the number of frames in an Opus packet"""
    data_pointer = ctypes.c_char_p(data)

    if length is None:
        length = len(data)

    result = libopus_packet_get_nb_frames(data_pointer, ctypes.c_int(length))

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return result


libopus_packet_get_samples_per_frame = \
    opuslib.api.libopus.opus_packet_get_samples_per_frame
libopus_packet_get_samples_per_frame.argtypes = (ctypes.c_char_p, ctypes.c_int)
libopus_packet_get_samples_per_frame.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def packet_get_samples_per_frame(
        data: bytes,
        fs: int
) -> typing.Union[int, typing.Any]:
    """Gets the number of samples per frame from an Opus packet"""
    data_pointer = ctypes.c_char_p(data)

    result = libopus_packet_get_nb_frames(data_pointer, ctypes.c_int(fs))

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return result


libopus_get_nb_samples = opuslib.api.libopus.opus_decoder_get_nb_samples
libopus_get_nb_samples.argtypes = (
    DecoderPointer,
    ctypes.c_char_p,
    ctypes.c_int32
)
libopus_get_nb_samples.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def get_nb_samples(
        decoder_state: ctypes.Structure,
        packet: bytes,
        length: int
) -> typing.Union[int, typing.Any]:
    """
    Gets the number of samples of an Opus packet.

    Parameters
    [in]	dec	OpusDecoder*: Decoder state
    [in]	packet	char*: Opus packet
    [in]	len	opus_int32: Length of packet

    Returns
    Number of samples

    Return values
    OPUS_BAD_ARG	Insufficient data was passed to the function
    OPUS_INVALID_PACKET	The compressed data passed is corrupted or of an
        unsupported type
    """
    result = libopus_get_nb_samples(decoder_state, packet, length)

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return result


libopus_decode = opuslib.api.libopus.opus_decode
libopus_decode.argtypes = (
    DecoderPointer,
    ctypes.c_char_p,
    ctypes.c_int32,
    opuslib.api.c_int16_pointer,
    ctypes.c_int,
    ctypes.c_int
)
libopus_decode.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def decode(  # pylint: disable=too-many-arguments
        decoder_state: ctypes.Structure,
        opus_data: bytes,
        length: int,
        frame_size: int,
        decode_fec: bool,
        channels: int = 2
) -> typing.Union[bytes, typing.Any]:
    """
    Decode an Opus Frame to PCM.

    Unlike the `opus_decode` function , this function takes an additional
    parameter `channels`, which indicates the number of channels in the frame.
    """
    _decode_fec = int(decode_fec)
    result: int = 0

    pcm_size = frame_size * channels * ctypes.sizeof(ctypes.c_int16)
    pcm = (ctypes.c_int16 * pcm_size)()
    pcm_pointer = ctypes.cast(pcm, opuslib.api.c_int16_pointer)

    result = libopus_decode(
        decoder_state,
        opus_data,
        length,
        pcm_pointer,
        frame_size,
        _decode_fec
    )

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return array.array('h', pcm_pointer[:result * channels]).tobytes()


libopus_decode_float = opuslib.api.libopus.opus_decode_float
libopus_decode_float.argtypes = (
    DecoderPointer,
    ctypes.c_char_p,
    ctypes.c_int32,
    opuslib.api.c_float_pointer,
    ctypes.c_int,
    ctypes.c_int
)
libopus_decode_float.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def decode_float(  # pylint: disable=too-many-arguments
        decoder_state: ctypes.Structure,
        opus_data: bytes,
        length: int,
        frame_size: int,
        decode_fec: bool,
        channels: int = 2
) -> typing.Union[bytes, typing.Any]:
    """
    Decode an Opus Frame.

    Unlike the `opus_decode` function , this function takes an additional
    parameter `channels`, which indicates the number of channels in the frame.
    """
    _decode_fec = int(decode_fec)

    pcm_size = frame_size * channels * ctypes.sizeof(ctypes.c_float)
    pcm = (ctypes.c_float * pcm_size)()
    pcm_pointer = ctypes.cast(pcm, opuslib.api.c_float_pointer)

    result = libopus_decode_float(
        decoder_state,
        opus_data,
        length,
        pcm_pointer,
        frame_size,
        _decode_fec
    )

    if result < 0:
        raise opuslib.exceptions.OpusError(result)

    return array.array('f', pcm[:result * channels]).tobytes()


libopus_ctl = opuslib.api.libopus.opus_decoder_ctl
libopus_ctl.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def decoder_ctl(
        decoder_state: ctypes.Structure,
        request,
        value=None
) -> typing.Union[int, typing.Any]:
    if value is not None:
        return request(libopus_ctl, decoder_state, value)
    return request(libopus_ctl, decoder_state)


destroy = opuslib.api.libopus.opus_decoder_destroy
destroy.argtypes = (DecoderPointer,)
destroy.restype = None
destroy.__doc__ = 'Frees an OpusDecoder allocated by opus_decoder_create()'

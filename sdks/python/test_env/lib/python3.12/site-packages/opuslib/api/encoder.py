#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
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


class Encoder(ctypes.Structure):  # pylint: disable=too-few-public-methods
    """Opus encoder state.
    This contains the complete state of an Opus encoder.
    """
    pass


EncoderPointer = ctypes.POINTER(Encoder)


libopus_get_size = opuslib.api.libopus.opus_encoder_get_size
libopus_get_size.argtypes = (ctypes.c_int,)  # must be sequence (,) of types!
libopus_get_size.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def get_size(channels: int) -> typing.Union[int, typing.Any]:
    """Gets the size of an OpusEncoder structure."""
    if channels not in (1, 2):
        raise ValueError('Wrong channels value. Must be equal to 1 or 2')
    return libopus_get_size(channels)


libopus_create = opuslib.api.libopus.opus_encoder_create
libopus_create.argtypes = (
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    opuslib.api.c_int_pointer
)
libopus_create.restype = EncoderPointer


def create_state(fs: int, channels: int, application: int) -> ctypes.Structure:
    """Allocates and initializes an encoder state."""
    result_code = ctypes.c_int()

    result = libopus_create(
        fs,
        channels,
        application,
        ctypes.byref(result_code)
    )

    if result_code.value is not opuslib.OK:
        raise opuslib.OpusError(result_code.value)

    return result


libopus_ctl = opuslib.api.libopus.opus_encoder_ctl
libopus_ctl.restype = ctypes.c_int


# FIXME: Remove typing.Any once we have a stub for ctypes
def encoder_ctl(
        encoder_state: ctypes.Structure,
        request,
        value=None
) -> typing.Union[int, typing.Any]:
    if value is not None:
        return request(libopus_ctl, encoder_state, value)
    return request(libopus_ctl, encoder_state)


libopus_encode = opuslib.api.libopus.opus_encode
libopus_encode.argtypes = (
    EncoderPointer,
    opuslib.api.c_int16_pointer,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int32
)
libopus_encode.restype = ctypes.c_int32


# FIXME: Remove typing.Any once we have a stub for ctypes
def encode(
        encoder_state: ctypes.Structure,
        pcm_data: bytes,
        frame_size: int,
        max_data_bytes: int
) -> typing.Union[bytes, typing.Any]:
    """
    Encodes an Opus Frame.

    Returns string output payload.

    Parameters:
    [in]	st	OpusEncoder*: Encoder state
    [in]	pcm	opus_int16*: Input signal (interleaved if 2 channels). length
        is frame_size*channels*sizeof(opus_int16)
    [in]	frame_size	int: Number of samples per channel in the input signal.
        This must be an Opus frame size for the encoder's sampling rate. For
            example, at 48 kHz the permitted values are 120, 240, 480, 960,
            1920, and 2880. Passing in a duration of less than 10 ms
            (480 samples at 48 kHz) will prevent the encoder from using the
            LPC or hybrid modes.
    [out]	data	unsigned char*: Output payload. This must contain storage
        for at least max_data_bytes.
    [in]	max_data_bytes	opus_int32: Size of the allocated memory for the
        output payload. This may be used to impose an upper limit on the
        instant bitrate, but should not be used as the only bitrate control.
        Use OPUS_SET_BITRATE to control the bitrate.
    """
    pcm_pointer = ctypes.cast(pcm_data, opuslib.api.c_int16_pointer)
    opus_data = (ctypes.c_char * max_data_bytes)()

    result = libopus_encode(
        encoder_state,
        pcm_pointer,
        frame_size,
        opus_data,
        max_data_bytes
    )

    if result < 0:
        raise opuslib.OpusError(
            'Opus Encoder returned result="{}"'.format(result))

    return array.array('b', opus_data[:result]).tobytes()


libopus_encode_float = opuslib.api.libopus.opus_encode_float
libopus_encode_float.argtypes = (
    EncoderPointer,
    opuslib.api.c_float_pointer,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int32
)
libopus_encode_float.restype = ctypes.c_int32


# FIXME: Remove typing.Any once we have a stub for ctypes
def encode_float(
        encoder_state: ctypes.Structure,
        pcm_data: bytes,
        frame_size: int,
        max_data_bytes: int
) -> typing.Union[bytes, typing.Any]:
    """Encodes an Opus frame from floating point input"""
    pcm_pointer = ctypes.cast(pcm_data, opuslib.api.c_float_pointer)
    opus_data = (ctypes.c_char * max_data_bytes)()

    result = libopus_encode_float(
        encoder_state,
        pcm_pointer,
        frame_size,
        opus_data,
        max_data_bytes
    )

    if result < 0:
        raise opuslib.OpusError(
            'Encoder returned result="{}"'.format(result))

    return array.array('b', opus_data[:result]).tobytes()


destroy = opuslib.api.libopus.opus_encoder_destroy
destroy.argtypes = (EncoderPointer,)  # must be sequence (,) of types!
destroy.restype = None
destroy.__doc__ = "Frees an OpusEncoder allocated by opus_encoder_create()"

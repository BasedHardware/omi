#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
#

import ctypes  # type: ignore

import opuslib.api

__author__ = 'Никита Кузнецов <self@svartalf.info>'
__copyright__ = 'Copyright (c) 2012, SvartalF'
__license__ = 'BSD 3-Clause License'


strerror = opuslib.api.libopus.opus_strerror
strerror.argtypes = (ctypes.c_int,)  # must be sequence (,) of types!
strerror.restype = ctypes.c_char_p
strerror.__doc__ = 'Converts an opus error code into a human readable string'


get_version_string = opuslib.api.libopus.opus_get_version_string
get_version_string.argtypes = None
get_version_string.restype = ctypes.c_char_p
get_version_string.__doc__ = 'Gets the libopus version string'

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Exceptions for OpusLib.
"""

import typing

import opuslib.api.info

__author__ = 'Никита Кузнецов <self@svartalf.info>'
__copyright__ = 'Copyright (c) 2012, SvartalF'
__license__ = 'BSD 3-Clause License'


class OpusError(Exception):

    """
    Generic handler for OpusLib errors from C library.
    """

    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__()

    # FIXME: Remove typing.Any once we have a stub for ctypes
    def __str__(self) -> typing.Union[str, typing.Any]:
        return str(opuslib.api.info.strerror(self.code))

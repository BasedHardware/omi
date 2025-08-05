#!/usr/bin/env python
# -*- coding: utf-8 -*-

# OpusLib Python Module.

"""
OpusLib Python Module.
~~~~~~~

Python bindings to the libopus, IETF low-delay audio codec

:author: Никита Кузнецов <self@svartalf.info>
:copyright: Copyright (c) 2012, SvartalF
:license: BSD 3-Clause License
:source: <https://github.com/onbeep/opuslib>

"""

from .exceptions import OpusError  # NOQA

from .constants import *  # NOQA

from .constants import OK, APPLICATION_TYPES_MAP  # NOQA

from .classes import Encoder, Decoder  # NOQA

__author__ = 'Никита Кузнецов <self@svartalf.info>'
__copyright__ = 'Copyright (c) 2012, SvartalF'
__license__ = 'BSD 3-Clause License'

#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

from mojostd import _canon, strip_leading_zeroes, is_canonical, is_canonical_modval, is_canonical_uniq
import std

std.is_canonical_modval = is_canonical_modval
std.is_canonical_uniq = is_canonical_uniq


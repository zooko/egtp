#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# This is a module to centralize debug-output.
# Hopefully its features will justify its use.

from mojostd import stderr, mojolog, generate_mojolog_filename, rotate_mojolog, cleanup_old_mojologs

import std

std.mojolog = mojolog

#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# $Id: std.py,v 1.1 2002/01/29 20:07:05 zooko Exp $

# This is a silly hack to get around Python's circular import limitation.
# See, standard modules like "debug", "humaneadable" and "idlib" all need to import each other, but should be in separate modules.
# (The loathsome `mojostd.py' module, pronounced "mojostupid", is an earlier klooge for the same purpose.)
# The `std.py' klooge is that each of those modules imports std at module import time, but then pokes a reference to its standard
# features *into* std so that other people can use those features (at runtime), with e.g. `std.hr()', `std.mojolog', `std.is_sloppy_id()', etc.

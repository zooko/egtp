#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: EGTPVersion.py,v 1.1 2002/01/29 22:40:29 zooko Exp $'

#
# This "module" should contain nothing else but EGTP_VERSION_STR
#
# ... and __cvsid...
# ... and a copyright notice so that nobody illegally copies our version numbers...
# TODO: make the line above this one funnier.

import os, string

EGTP_VERSION_TUP=(0,0,2,)
EGTP_VERSION_STR=string.join(map(str, EGTP_VERSION_TUP), ".")

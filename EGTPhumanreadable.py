#!/usr/bin/env python

#
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# CVS:
__cvsid = '$Id: EGTPhumanreadable.py,v 1.1 2002/01/29 20:07:05 zooko Exp $'

# standard modules

# pyutil modules
import humanreadable

true = 1
false = 0

class EGTPRepr(humanreadable.BetterRepr):
    """
    @subclasses BetterRepr and represents 20-byte "unique ID" strings as "<abcde>" base-32 abbreviations.
    """
    def __init__(self):
        BetterRepr.__init__(self)
        self.repr_string = self.repr_str

    def repr_str(self, obj, level, asciihashmatch=_asciihash_re.match, b2a=b2a, translate=translate, nulltrans=nulltrans, printableascii=printableascii):
        if len(obj) == 20:
            # But maybe it was just a 20-character human-readable string, like "credit limit reached", so this is an attempt to detect that case.
            if len(translate(obj, nulltrans, printableascii)) == 0:
                if self.maxourstring >= 22:
                    return `obj`

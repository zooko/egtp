#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: loggedthreading.py,v 1.1 2002/01/29 20:07:07 zooko Exp $'

# standard modules
from threading import *
import traceback

# our modules
import debug

# remove stuff from our namespace to allow a polite 'from X import *'
_print_exc = traceback.print_exc
del traceback
_debug_mojolog = debug.mojolog
del debug


class LoggedThread(Thread):
    """
    A descendent of threading.Thread() that overrides the run() method
    to log all thread terminating exceptions using debug.mojolog rather
    than normal mojolog as the threading module does.
    NOTE: this won't be useful if you override the run() method.
    """
    def run(self):
        try:
            Thread.run(self)
        except:
            _debug_mojolog.write('Exception in thread \'%s\':\n' % (self.getName(),), vs='ERROR')
            _print_exc(file=_debug_mojolog)


def test_this():
    def funct():
        print 42
        raise "sixtynine dude!"
    l = LoggedThread(target=funct)
    l.start()
    import time
    time.sleep(1)

if __name__ == '__main__':
    test_this()

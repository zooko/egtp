#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
import evilcryptopp

__doc__ = evilcryptopp._randsource_doc
get = evilcryptopp._randsource_get

import time
import sys
import os
import sha
import string

if sys.platform == 'win32':
    # this is part of the win32all python package, get it from:
    # http://www.activestate.com/Products/ActivePython/win32all.html
    import win32api

# our modules

def add(seedbytes, entropybits):
    evilcryptopp._randsource_add(seedbytes, entropybits)
   

# TODO add entropy gathering for other OSes
if sys.platform == "win32" :
    print 'WARNING: a better random entropy source is needed for this OS\n'
    # Anyone know good ways to gather more starting entropy on windows? 
    shabits = sha.sha()
    shabits.update(str(win32api.GetCursorPos()))
    shabits.update(str(time.time()))
    shabits.update(sys.exec_prefix)
    shabits.update(str(time.time()))
    shabits.update(str(win32api.GetCursorPos()))
    shabits.update(str(os.environ))
    shabits.update(str(win32api.GetCursorPos()))
    shabits.update(str(time.time()))
    shabits.update(str(win32api.GetCurrentProcessId()))
    shabits.update(str(sys.dllhandle))
    add(shabits.digest(), 160)
elif string.find(sys.platform, "linux") >= 0 :
    urandomdata = open('/dev/urandom', 'rb').read(20)
    add(urandomdata, len(urandomdata)*8)
elif string.find(string.lower(sys.platform), "bsd") >= 0 :
    urandomdata = open('/dev/urandom', 'rb').read(20)
    add(urandomdata, len(urandomdata)*8)
else :
    print 'WARNING: a better random entropy source is needed for this OS\n'
    add(sha.sha( sys.platform + sys.version + str(time.time()) ).digest(), 160)

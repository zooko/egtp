#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: EGTPtest.py,v 1.3 2002/03/11 17:35:16 zooko Exp $'

# standard Python modules
import threading

# pyutil modules
import DoQ
import config
from debugprint import debugprint
from humanreadable import hr

# libbase32 modules
# from humread import hr # XXX for when we switch to base32 encoding...

# MN modules
from confutils import confman
import idlib
from interfaces import *
import mencode

# EGTP modules
import CommStrat
import Node

true = 1
false = 0

finishedflag = threading.Event() # This gets set when we are done with the test and it is okay for the Python interpreter to exit.

confman['MAX_VERBOSITY'] = 0
config.MAX_VERBOSITY = 0

# a lookup man which uses only local data;  In a real app you need remote lookup in the form of MetaTrackers, Chord, Plex, Alpine, or something.
class LocalLookupMan(ILookupManager):
    def __init__(self):
        self.data = {}
    def lookup(self, key, lookuphand):
        serialized = mencode.mencode(key)
        if self.data.has_key(serialized):
            lookuphand.result(self.data.get(serialized))
        else:
            lookuphand.fail()
        return # `lookup()' never returns any return value!
    def register_address(self, egtpid, egtpaddr):
        assert idlib.equal(egtpid, CommStrat.addr_to_id(egtpaddr))
        self.data[mencode.mencode({'type': "EGTP address", 'key': egtpid})] = egtpaddr

# a discovery man which uses only local data;  In a real app you need distributed discovery in the form of MetaTrackers, Plex, Alpine, or something.
class LocalDiscoveryMan(IDiscoveryManager):
    def __init__(self):
        self.data = {}
    def discover(self, key, discoveryhand):
        serialized = mencode.mencode(key)
        discoveryhand.result(self.data.get(serialized))
        return # `discover()' never returns any return value!

def test_1():
    localLM = LocalLookupMan()
    localDM = LocalDiscoveryMan()

    # make a listener
    l = Node.Node(allownonrouteableip=true, lookupman=localLM, discoveryman=localDM) # `allownonrouteableip' means: tell it to do TCP even if you are not routeable from the real Internet (for testing)

    # get its "EGTP address" record, which includes its public key and a set of protocols+addresses by which it can be reached
    lsaddr = l.get_address()

    lsid = CommStrat.addr_to_id(lsaddr)
    localLM.register_address(lsid, lsaddr)

    # set a handler func: if any messages come in with message type "ping", the EGTP Node will call this function.
    def l_ping_handler(sender, msg):
        debugprint("yyy EGTPtest: Got a message from %s.  The message says: %s\n", args=(sender, msg,))
        finishedflag.set()

    l.set_handler_func(mtype="ping", handler_func=l_ping_handler)

    # make a second EGTP Node for sending
    s = Node.Node(lookupman=localLM, discoveryman=localDM)

    # have the 2nd node ping the first
    debugprint("yyy EGTPtest: about to send!\n")
    s.send(lsid, mtype="ping", msg="hello there, number one!")
    debugprint("yyy EGTPtest: sent!\n")

# Create the event queue for this process:
DoQ.doq = DoQ.DoQ()
# Call `init()'.
Node.init()
DoQ.doq.add_task(test_1)

while not finishedflag.isSet():
    finishedflag.wait(3)

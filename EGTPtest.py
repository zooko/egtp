#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: EGTPtest.py,v 1.5 2002/03/13 17:43:32 zooko Exp $'

# standard Python modules
import threading

# pyutil modules
import DoQ
import config
from debugprint import debugprint
from humanreadable import hr
from timeutil import timer

# libbase32 modules
# from humread import hr # XXX for when we switch to base32 encoding...

# (old) MN modules
from confutils import confman
import idlib
from interfaces import *
import mencode

# EGTP modules
import CommStrat
import Node

true = 1
false = 0

confman['MAX_VERBOSITY'] = 0
config.MAX_VERBOSITY = 0

# a lookup man which uses only local data;  In a real app you need remote lookup in the form of MetaTrackers, Tristero, Chord, Plex, Alpine, or something.
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

# a discovery man which uses only local data;  In a real app you need distributed discovery in the form of MetaTrackers, Tristero, Plex, Alpine, or something.
class LocalDiscoveryMan(IDiscoveryManager):
    def __init__(self):
        self.data = {}
    def discover(self, key, discoveryhand):
        serialized = mencode.mencode(key)
        discoveryhand.result(self.data.get(serialized))
        return # `discover()' never returns any return value!

def _help_test(finishedflag, numsuccessesh, lm, dm):
    """
    @param lm an object that satisfies the ILookupMan interface
    @param dm an object that satisfies the IDiscoveryMan interface
    """
    start = timer.time()

    # Make a listener.  He will announce his EGTP address to the lookupman `lm'.
    n1 = Node.Node(allownonrouteableip=true, lookupman=lm, discoveryman=dm)

    # Set a handler func: if any messages come in with message type "ping", the EGTP Node will call this function.
    def l_ping_handler(sender, msg, finishedflag=finishedflag, numsuccessesh=numsuccessesh, start=start):
        debugprint("_help_test(): passed in %s seconds: Got a message from %s.  The message says: %s\n", args=("%0.1f" % (timer.time() - start), sender, msg,), v=0)
        numsuccessesh[0] += 1
        finishedflag.set()

    n1.set_handler_func(mtype="ping", handler_func=l_ping_handler)

    # Make a sender.  He'll keep a reference to `lm' for later use.
    n2 = Node.Node(allownonrouteableip=true, lookupman=lm, discoveryman=dm)

    # Have the second node ping the first, using only the first's id.
    n2.send(n1.get_address().get_id(), mtype="ping", msg="hello there, you crazy listener!")

def test_0(finishedflag, numsuccessesh):
    """
    This is testing obsolete behavior, but egtp doesn't yet pass test_1(), which tests the new behavior...
    """
    start = timer.time()

    localLM = LocalLookupMan()
    localDM = LocalDiscoveryMan()

    # make a listener
    l = Node.Node(allownonrouteableip=true, lookupman=localLM, discoveryman=localDM) # `allownonrouteableip' means: tell it to do TCP even if you are not routeable from the real Internet (for testing)
    
    # get its "EGTP address" record, which includes its public key and a set of protocols+addresses by which it can be reached
    lsaddr = l.get_address()

    lsid = CommStrat.addr_to_id(lsaddr)
    localLM.register_address(lsid, lsaddr)

    # set a handler func: if any messages come in with message type "ping", the EGTP Node will call this function.
    def l_ping_handler(sender, msg, finishedflag=finishedflag, numsuccessesh=numsuccessesh, start=start):
        debugprint("test_0: passed in %s seconds: Got a message from %s.  The message says: %s\n", args=("%0.1f" % (timer.time() - start), sender, msg,), v=0)
        numsuccessesh[0] += 1
        finishedflag.set()

    l.set_handler_func(mtype="ping", handler_func=l_ping_handler)

    # make a second EGTP Node for sending
    s = Node.Node(lookupman=localLM, discoveryman=localDM)

    # have the 2nd node ping the first
    debugprint("test_0: about to send!\n", v=0)
    s.send(lsid, mtype="ping", msg="hello there, number one!")
    debugprint("test_0: sent!\n", v=0)

def test_1(finishedflag, numsuccessesh):
    localLM = LocalLookupMan()
    localDM = LocalDiscoveryMan()
    _help_test(finishedflag, numsuccessesh, localLM, localDM)

def runalltests(tests, expectedfailures=0):
    if expectedfailures > 0:
        print "WARNING: this module is currently failing some of the unit tests.  Number of expected failures: %s" % expectedfailures

    # Create the event queue for this process:
    DoQ.doq = DoQ.DoQ()
    # Call `init()'.
    Node.init()

    numsuccessesh = [0]
    ts = []
    for test in tests:
        finishedflag = threading.Event()
        ts.append((test, finishedflag,))
        DoQ.doq.add_task(test, args=(finishedflag, numsuccessesh,))

    timeout = 20
    for (test, finishedflag,) in ts:
        tstart = timer.time()
        while not finishedflag.isSet():
            if (timer.time() - tstart) < timeout:
                finishedflag.wait(1)
            else:
                print "test %s didn't finish within %s seconds" % (test, timeout,)
                break

    assert numsuccessesh[0] == len(tests), "not all tests passed: num successes: %s, num failures: %s" % (numsuccessesh[0], map(lambda x: x[0], filter(lambda x: not x[1].isSet(), ts)),)

runalltests((test_0, test_1,), expectedfailures=1)


#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: EGTPtest.py,v 1.11 2002/06/25 03:54:57 zooko Exp $'

# standard Python modules
import threading, types

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

# EGTP modules
import CommStrat
import Node
import NodeLookupMan
from TristeroLookup import TristeroLookup
from interfaces import *

true = 1
false = 0

confman['MAX_VERBOSITY'] = 0
config.MAX_VERBOSITY = 0

# a lookup man which uses only local data;  In a real app you need remote lookup in the form of MetaTrackers, Tristero, Chord, Plex, Alpine, or something.
class LocalLookupMan(ILookupManager):
    def __init__(self):
        self.data = {}
    def lookup(self, key, lookuphand):
        if self.data.has_key(key):
            lookuphand.result(self.data.get(key))
        else:
            lookuphand.done(failure_reason="unexpected failure to find value in local dict")
        return # `lookup()' never returns any return value!
    def publish(self, egtpid, egtpaddr):
        """
        @precondition egtpid must be an id.: idlib.is_id(egtpid): "egtpid: %s :: %s" % (hr(egtpid), hr(type(egtpid)),)
        @precondition egtpaddr must be a dict.: type(egtpaddr) is types.DictType: "egtpaddr: %s :: %s" % (hr(egtpaddr), hr(type(egtpaddr)),)
        @precondition egtpid must match egtpaddr.: idlib.equal(egtpid, CommStrat.addr_to_id(egtpaddr)): "egtpid: %s, egtpaddr: %s" % (hr(egtpid), hr(egtpaddr), hr(egtpaddr.get_id(),))
        """
        assert idlib.is_id(egtpid), "precondition: egtpid must be an id." + " -- " + "egtpid: %s :: %s" % (hr(egtpid), hr(type(egtpid)),)
        assert type(egtpaddr) is types.DictType, "precondition: egtpaddr must be a dict." + " -- " + "egtpaddr: %s :: %s" % (hr(egtpaddr), hr(type(egtpaddr)),)
        assert idlib.equal(egtpid, CommStrat.addr_to_id(egtpaddr)), "precondition: egtpid must match egtpaddr." + " -- " + "egtpid: %s, egtpaddr: %s" % (hr(egtpid), hr(egtpaddr), hr(egtpaddr.get_id(),))

        self.data[egtpid] = egtpaddr

# a discovery man which uses only local data;  In a real app you need distributed discovery in the form of MetaTrackers, Tristero, Plex, Alpine, or something.
class LocalDiscoveryMan(IDiscoveryManager):
    def __init__(self):
        self.data = {}
    def discover(self, key, discoveryhand):
        discoveryhand.result(self.data.get(key))
        return # `discover()' never returns any return value!

def _help_test(finishedflag, numsuccessesh, lm, dm, name="a test"):
    """
    @param lm an object that satisfies the ILookupMan interface
    @param dm an object that satisfies the IDiscoveryMan interface
    """
    start = timer.time()

    # Make a listener.  He will announce his EGTP address to the lookupman `lm'.
    n1 = Node.Node(allownonrouteableip=true, lookupman=lm, discoveryman=dm)

    # Set a handler func: if any messages come in with message type "ping", the EGTP Node will call this function.
    def l_ping_handler(sender, msg, finishedflag=finishedflag, numsuccessesh=numsuccessesh, start=start, name=name):
        debugprint("%s(): passed in %s seconds: Got a message from %s.  The message says: %s\n", args=(name, "%0.1f" % (timer.time() - start), sender, msg,), v=0)
        numsuccessesh[0] += 1
        finishedflag.set()

    n1.set_handler_func(mtype="ping", handler_func=l_ping_handler)

    # Make a sender.  He'll keep a reference to `lm' for later use.
    n2 = Node.Node(allownonrouteableip=true, lookupman=lm, discoveryman=dm)

    # Have the second node ping the first, using only the first's id.
    n2.send(CommStrat.addr_to_id(n1.get_address()), mtype="ping", msg="hello there, you crazy listener!")

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

    timeout = 60
    for (test, finishedflag,) in ts:
        tstart = timer.time()
        while not finishedflag.isSet():
            if (timer.time() - tstart) < timeout:
                finishedflag.wait(1)
            else:
                print "test %s didn't finish within %s seconds" % (test, timeout,)
                break

    assert numsuccessesh[0] == len(tests), "not all tests passed: num successes: %s, num failures: %s" % (numsuccessesh[0], map(lambda x: x[0], filter(lambda x: not x[1].isSet(), ts)),)

def test_local(finishedflag, numsuccessesh):
    localLM = NodeLookupMan.NodeLookupMan(LocalLookupMan())
local   localDM = LocalDiscoveryMan()
    _help_test(finishedflag, numsuccessesh, localLM, localDM, name="test_local")

def test_tristero_lookup(finishedflag, numsuccessesh):
    localLM = TristeroLookup("http://fnordovax.dyndns.org:10805")
    print 'TristeroLookup Service:', localLM
    localDM = LocalDiscoveryMan()
    _help_test(finishedflag, numsuccessesh, localLM, localDM, name="test_tristero_lookup")

runalltests((test_local, test_tristero_lookup,), expectedfailures=0)


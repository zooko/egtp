#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import UserDict
import asyncore
import os
import socket
import string
import struct
import threading
import time
import traceback
import types

# pyutil modules
from config import DEBUG_MODE, REALLY_SLOW_DEBUG_MODE
from debugprint import debugprint
import pyutilasync

# (old-)EGTP modules
import BandwidthThrottler
import Cache
import CommsError
from CommHints import HINT_EXPECT_RESPONSE, HINT_EXPECT_MORE_TRANSACTIONS, HINT_EXPECT_NO_MORE_COMMS, HINT_EXPECT_TO_RESPOND, HINT_THIS_IS_A_RESPONSE, HINT_NO_HINT
import CommStrat
import DoQ
import LazySaver
import TCPConnection
import confutils
import idlib
import mojoutil
from mojoutil import bool
from confutils import confman
import ipaddresslib
from humanreadable import hr

true = 1
false = None

SECS_BETWEEN_IPADDR_RECHECK = 180   # recheck our IP address every 3 minutes incase it has changed

class TCPCommsHandler(asyncore.dispatcher, LazySaver.LazySaver):
    """
    This accepts incoming connections and spawns off a TCPConnection for each one.
    """
    def __init__(self, mtm, listenport=None, pickyport=false, dontbind=false):
        """
        @param listenport the preferred port to listen on
        @param pickyport `true' if you want to fail in the case that `listenport' is unavailable, false if you want to get another arbitrary port

        @precondition `listenport' must be a non-negative integer or `None'.: (listenport is None) or ((type(listenport) is types.IntType) and (listenport > 0)): "listenport: %s :: %s" % (hr(listenport), `type(listenport)`)
        @precondition `pickyport' is false or listenport is an integer.: (not pickyport) or (type(listenport) is types.IntType)
        """
        assert (listenport is None) or ((type(listenport) is types.IntType) and (listenport > 0)), "precondition: `listenport' must be a non-negative integer or `None'." + " -- " + "listenport: %s :: %s" % (hr(listenport), `type(listenport)`)
        assert (not pickyport) or (type(listenport) is types.IntType), "precondition: `pickyport' is false or listenport is an integer."

        asyncore.dispatcher.__init__(self)

        # map cid to instance of CommStrat
        self._cid_to_cs = {}
        # map id to "not yet"/"yes"
        self._cids_to_activation = {}

        self._mtm = mtm
           
        self._requested_listenport = listenport
        self._pickyport = pickyport

        self._conncache = TCPConnCache(cid_to_cs=self._cid_to_cs)

        # this boolean determines if we actually bind to a port
        self._dontbind = dontbind

        self._throttlerout = BandwidthThrottler.BandwidthThrottler(throttle=confman.is_true_bool(('TCP_THROTTLE_OUT',)), Kbps=mojoutil.longpopL(confman.get('TCP_MAX_KILOBITS_PER_SECOND_OUT', "56")))
        self._throttlerin = BandwidthThrottler.BandwidthThrottler(throttle=confman.is_true_bool(('TCP_THROTTLE_IN',)), Kbps=mojoutil.longpopL(confman.get('TCP_MAX_KILOBITS_PER_SECOND_IN', "56")))
        self._throttlerin.register(self._throttle, self._unthrottle)

        # My "id" is just a random number.  Nobody really uses this except for testing.
        self._id = idlib.make_new_random_id(thingtype='TCPCommsHandler')

        self._upward_inmsg_handler = None

        self._islistening = false
        self.readable = self._readable_false
        self._throttled = false

        # If you are bound to a port and listening, then `self._islistening' will be `true'.

        # If you want to see if your address is routable or not, then call `ipaddresslib.is_routable(self._ip)', but you should
        # only do this from within TCPCommsHandler.  If you are writing higher-level code, and you want to see if
        # you have a good comm strat, then just call `get_comm_strategy()' and see if you like the strategy offered.
        # TCPCommsHandler will give you back a "CommStrat.TCP" (or, in the worst case, a "CommStrat.Pickup",
        # which you almost certainly do not like).  Call `ipaddresslib.is_routable(cs.host)'.  The reason to go through the
        # CommStrat abstraction and not just peek at `self._ip' is because people can set up tunnels and announce
        # themselves as being available on a different host/port.

        # self._ip = None # persistent -- it gets initialized only once in the persistent life of the broker -- not every time the broker process is started.  So don't comment this back in, it is just here for documetary purposes.
        # self._listenport = None # persistent -- it gets initialized only once in the persistent life of the broker -- not every time the broker process is started.  So don't comment this back in, it is just here for documetary purposes.

        LazySaver.LazySaver.__init__(self, fname=os.path.join(self._mtm._dbdir, 'ListenerManager.pickle'), attrs={'_ip': None, '_listenport': None}, DELAY=10*60)

    def _bandwidth_tick_doq_loop(self):
        pyutilasync.selector.add_task(self._throttlerout.used, args=(0,))
        pyutilasync.selector.add_task(self._throttlerin.used, args=(0,))
        DoQ.doq.add_task(self._bandwidth_tick_doq_loop, delay=60)

    def shutdown(self):
        self._throttlerin.unregister(self._throttle, self._unthrottle)
        self.stop_listening()
        LazySaver.LazySaver.shutdown(self)
        self._cid_to_cs = None
        self._cid_to_activation = None

    def stop_listening(self):
        # ignore an AttributeError in asyncore when this TCPCommsHandler is a dummy for outgoing only without a socket
        so = self
        try:
            while hasattr(so, 'socket'):
                so = getattr(so, 'socket')
            so.close()
        except AttributeError:
            # whoops.  Well, nevermind.
            pass
        self._islistening = false
        self.readable = self._readable_false

        # Clean up all outstanding connections.
        for k in self._conncache.keys():
            self._conncache.remove(k)

    def is_listening(self):
        return self._islistening

    def start_listening(self, inmsg_handler_func):
        """
        @precondition `inmsg_handler_func' must be callable.: callable(inmsg_handler_func): "inmsg_handler_func: %s :: %s" % (hr(inmsg_handler_func), hr(type(inmsg_handler_func)),)
        """
        assert callable(inmsg_handler_func), "precondition: `inmsg_handler_func' must be callable." + " -- " + "inmsg_handler_func: %s :: %s" % (hr(inmsg_handler_func), hr(type(inmsg_handler_func)),)

        self._upward_inmsg_handler = inmsg_handler_func

        # if dontbind is set, do nothing here, we don't want to listen
        if self._dontbind :
            return

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()

        if self._pickyport:
            try:
                self.bind(("", self._requested_listenport))
            except socket.error:
                raise CommsError.CannotListenError, "couldn't bind to port, and I'm picky about which port I listen on"

            self._listenport = self._requested_listenport
        else:
            newlistenport = None # Will be set to the port number only after we've bound to it.

            MAX_PORT = 32767 # standard?  But you can feel free to change it without changing the rest of this code.
            MIN_PORT = 1025 # Arbitrarily chosen.  Change at your whim and you don't need to change the rest of this code.  (But be aware that ports below 1024 are usually reserved by the OS.)
            if self._requested_listenport:
                try_listenport = self._requested_listenport
            else:
                try_listenport = 20001 # Arbitrarily chosen.  Change at your whim and you don't need to change the rest of this code.
            firstporttried = try_listenport

            while not newlistenport:
                try:
                    self.bind(("", try_listenport))
                    debugprint("successfully bound to port %s.\n", args=(try_listenport,), v=1, vs="TCPCommsHandler")
                    newlistenport = try_listenport

                except socket.error:
                    debugprint("couldn't bind to port %s; trying next port.\n", args=(try_listenport,), v=1, vs="TCPCommsHandler")

                    try_listenport = ((try_listenport + 1 - MIN_PORT) % (MAX_PORT + 1 - MIN_PORT)) + MIN_PORT

                    if try_listenport == firstporttried:
                        # Well, we've tried them all!  Give up.
                        raise CommsError.CannotListenError, "couldn't bind to any port"
            self._listenport = newlistenport

        self.listen(int(confman['TCP_MAX_CONNECTIONS']))

        self._ip = ipaddresslib.get_primary_ip_address(nonroutableok=true)
        debugprint("successfully bound to port %s.\n", args=(try_listenport,), v=1, vs="TCPCommsHandler")
        self._islistening = true
        # Now if we are not throttled then we are now ready to accept connections.
        if not self._throttled:
            self.readable = self._readable_true

        self._lazy_save()

        # Now start a DoQ loop to recheck IP address every SECS_BETWEEN_IPADDR_RECHECK seconds...
        DoQ.doq.add_task(self._recheck_ip_address, delay=SECS_BETWEEN_IPADDR_RECHECK)

        assert self._listenport > 0
        debugprint("I am listening on port %s and telling %s.\n", args=(self._listenport, inmsg_handler_func), v=4, vs="TCPCommsHandler")

    def _recheck_ip_address(self):
        if not self._islistening:
            return

        # this rechecks our IP address every so often in case it has changed
        newip = ipaddresslib.get_primary_ip_address(nonroutableok=true)
        if newip != self._ip:
            # It changed!  Announce new one to the world.
            self._mtm.send_hello_to_meta_trackers()
            self._lazy_save()

        # DoQ loop:
        DoQ.doq.add_task(self._recheck_ip_address, delay=SECS_BETWEEN_IPADDR_RECHECK)

    def get_comm_strategy(self):
        if self._islistening:
            # Now IP_ADDRESS_OVERRIDE overrides the actual bound IP address, and TRANSACTION_MANAGER_ANNOUNCED_PORT overrides the actual bound port.
            announceip = confman.get('IP_ADDRESS_OVERRIDE')
            if not announceip:
                announceip = self._ip
            if confman.get('TRANSACTION_MANAGER_ANNOUNCED_PORT'):
                announceport = int(confman['TRANSACTION_MANAGER_ANNOUNCED_PORT'])
            else:
                announceport = self._listenport

            return CommStrat.TCP(tcpch=self, broker_id=self._mtm.get_id(), host=announceip, port=announceport)
        else:
            return None

    def get_id(self):
        return self._id
       
    def send_msg(self, counterparty_id, msg, hint=HINT_NO_HINT, fast_fail_handler=None, timeout=None):
        """
        """
        counterparty_id = idlib.to_binary(counterparty_id)  # this also checks the precondition of counterparty_id being an id

        if self._cids_to_activation.get(counterparty_id) == "not yet":
            try:
                cs = self._cid_to_cs[counterparty_id]
            except KeyError:
                debugprint("%s._cis_to_cs did not contain %s (%s)\nkeys: %s\n" % (self, `counterparty_id`, hr(counterparty_id), `self._cid_to_cs.keys()`))
                raise
            self._activate_commstrat(counterparty_id, cs)
            # QUERY: but what if _activate_commstrat failed? (such as a TCP connection that couldn't
            # be established)  This would mean that we think we have an active connection to them when we don't.

            # Zooko responds:  We don't have any notion of an active connection in the
            # higher-layer code.  There is, for example, no "connection problem" error, only
            # a "could not send" error.  You just tell the comms handler to use a connection
            # strategy and then you try to send and the earliest that you can find out that
            # the strategy is bad is when you can't send.  This is actually considered to be
            # a feature-not-a-bug -- our code for finding new connection strategies is
            # executed only lazily (when we try to send and fail), rather than eagerly
            # (whenever we get a connection strategy).  So for example you can remember for
            # weeks and weeks that the connection strategy to talk to <EZR> is a certain TCP
            # address, and every day or two you send <EZR> a message, and fortunately <EZR>
            # happens to be on-line each time, so the message gets through.  Now the fact is
            # that <EZR> is off-line most of the rest of the time and trying to activate the
            # connection strategy would fail, but you don't care.  --Zooko 2000-07-22

            self._cids_to_activation[counterparty_id] = "yes"

        tcpc = self._conncache.get(counterparty_id)

        cs = self._cid_to_cs.get(counterparty_id)
        # debugprint("%s._cid_to_cs.get(%s) -> %s\n", args=(self, counterparty_id, cs,))
        if cs:
            # assert (tcpc is None) or (cs.asyncsock is tcpc), "counterparty_id: %s, cs: %s, cs.asyncsock: %s, tcpc: %s" % (hr(counterparty_id), hr(cs), hr(cs.asyncsock), hr(tcpc),)
            if not ((tcpc is None) or (cs.asyncsock is tcpc)):
                debugprint("not ((tcpc is None) or (cs.asyncsock is tcpc)) -- counterparty_id: %s, cs: %s, cs.asyncsock: %s, tcpc: %s\n", args=(counterparty_id, cs, cs.asyncsock, tcpc,), v=0, vs="PSEUDOASSERTION")
            if tcpc is None:
                tcpc = cs.asyncsock

            # If we were expecting to send a response and this is it...
            if (hint & HINT_THIS_IS_A_RESPONSE) and (cs.hint & HINT_EXPECT_TO_RESPOND) and (cs.hintnumexpectedsends > 0):
                cs.hintnumexpectedsends = cs.hintnumexpectedsends - 1
                if cs.hintnumexpectedsends == 0:
                    cs.hint = cs.hint & (~ HINT_EXPECT_TO_RESPOND)

            if hint & HINT_EXPECT_RESPONSE:
                cs.hintnumexpectedresponses = cs.hintnumexpectedresponses + 1

            cs.hint = cs.hint | hint & (~ HINT_THIS_IS_A_RESPONSE)

        if not tcpc:
            raise CommsError.CannotSendError, ("no TCP connection", cs,)

        assert isinstance(tcpc, TCPConnection.TCPConnection)
        tcpc.send(msg, fast_fail_handler)
        del msg  # we're done with it, encourage faster gc

        # Now if we have a hint that says no response is expected, close the connection.
        if cs and (cs.hint & HINT_EXPECT_NO_MORE_COMMS):
            pn = None
            try:
                pn = tcpc.getpeername()
            except:
                pass

            debugprint("TCPCommsHandler._internal_send_msg(): removing connection %s _cid_for_debugging: %s, .getpeername(): %s due to HINT_EXPECT_NO_MORE_COMMS.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
            self._conncache.remove(counterparty_id)

        self._conncache._cleanup_nice()

    def forget_comm_strategy(self, counterparty_id, commstrat=None):
        curcs = self._cid_to_cs.get(counterparty_id)
        if (curcs is None) or (commstrat and not curcs.same(commstrat)):
            # We aren't using `commstrat', so there is nothing to forget.
            debugprint("TCPCommsHandler was asked to forget unknown commstrat: %s, curcs: %s\n", args=(commstrat, curcs,), v=5, vs="debug")
            return

        # debugprint("TCPCommsHandler: Forgetting comm strategy.  counterparty_id: %s, curcs: %s\n", args=(counterparty_id, curcs,), v=6, vs="commstrats")

        remmed = self._conncache.remove_if_present(counterparty_id)
        # assert (remmed is None) or (remmed is curcs.asyncsock), "counterparty_id: %s, curcs: %s, remmed: %s" % (hr(counterparty_id), hr(curcs), hr(remmed))
        if not ((remmed is None) or remmed._closing or (remmed is curcs.asyncsock)):
            debugprint("not ((remmed is None) or remmed._closing or (remmed is curcs.asyncsock)), counterparty_id: %s, curcs: %s, remmed: %s\n", args=(counterparty_id, curcs, remmed,), v=0, vs="PSEUDOASSERTION")

        del self._cid_to_cs[counterparty_id]
        del self._cids_to_activation[counterparty_id]

    def use_comm_strategy(self, counterparty_id, commstrat):
        """
        @precondition `counterparty_id' must be a binary id.: idlib.is_binary_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        @precondition `commstrat' must be a CommStrat.TCP.: isinstance(commstrat, CommStrat.TCP): "commstrat: %s :: %s" % (hr(commstrat), hr(type(commstrat)))
        @precondition If `commstrat' already has an open TCP socket then the `commstrat' must be part of this TCPCommsHandler.: (commstrat.asyncsock is None) or (commstrat._tcpch is self): "counterparty_id: %s, commstrat: %s, self._conncache.get(counterparty_id): %s, commstrat._tcpch: %s, self: %s" % (hr(counterparty_id), hr(commstrat), hr(self._conncache.get(counterparty_id)), hr(commstrat._tcpch), hr(self),)
        """
        assert idlib.is_binary_id(counterparty_id), "precondition: `counterparty_id' must be a binary id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)
        assert isinstance(commstrat, CommStrat.TCP), "precondition: `commstrat' must be a CommStrat.TCP." + " -- " + "commstrat: %s :: %s" % (hr(commstrat), hr(type(commstrat)))
        assert (commstrat.asyncsock is None) or (commstrat._tcpch is self), "precondition: If `commstrat' already has an open TCP socket then the `commstrat' must be part of this TCPCommsHandler." + " -- " + "counterparty_id: %s, commstrat: %s, self._conncache.get(counterparty_id): %s, commstrat._tcpch: %s, self: %s" % (hr(counterparty_id), hr(commstrat), hr(self._conncache.get(counterparty_id)), hr(commstrat._tcpch), hr(self),)

        assert (commstrat.asyncsock is None) or (commstrat.asyncsock._closing) or (commstrat.asyncsock in self._conncache.values()), "commstrat.asyncsock: %s, self._conncache.items(): %s" % (hr(commstrat.asyncsock), hr(self._conncache.items()),)

        # debugprint("%s.use_comm_strategy(%s, %s)\n", args=(self, counterparty_id, commstrat,))

        curcs = self._cid_to_cs.get(counterparty_id)

        preffedcs = CommStrat.choose_best_strategy(curcs, commstrat)
        # debugprint("CommStrat.choose_best_strategy(curcs: %s, commstrat: %s) -> %s\n", args=(curcs, commstrat, preffedcs,))

        if (preffedcs is not curcs) and (curcs is not None):
            self.forget_comm_strategy(counterparty_id, curcs)

        if preffedcs is commstrat:
            commstrat._tcpch = self

            # debugprint("%s._cid_to_cs[%s] = %s\n", args=(self, counterparty_id, commstrat,))
            if self._cid_to_cs.get(counterparty_id) is not commstrat:
                self._cid_to_cs[counterparty_id] = commstrat
                self._cids_to_activation[counterparty_id] = "not yet"

            if commstrat.asyncsock:
                commstrat.asyncsock._cid_for_debugging = counterparty_id
                self._conncache.insert(counterparty_id, commstrat.asyncsock)

    def _activate_commstrat(self, counterparty_id, cs):
        """
        @precondition `self._upward_inmsg_handler' must be callable.: callable(self._upward_inmsg_handler): "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
        """
        assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)

        # debugprint("TCPCommsHandler._activate_commstrat(%s, %s) stack: %s\n", args=(counterparty_id, cs, traceback.extract_stack(),), v=7, vs="commstrats") # verbose -- commstrats -- traceback.extract_stack() is very slow.
        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')  # this also checks the precondition of counterparty_id being an id

        if cs.asyncsock and (not cs.asyncsock._closing):
            assert isinstance(cs.asyncsock, TCPConnection.TCPConnection), "cs.asyncsock: %s :: %s" % (hr(cs.asyncsock), hr(type(cs.asyncsock)))
            tcpc = cs.asyncsock
            tcpc._upward_inmsg_handler=self._inmsg_handler
        elif cs.host and cs.port:
            tcpc = TCPConnection.TCPConnection(inmsg_handler_func=self._inmsg_handler, close_handler_func=self._close_handler, key=counterparty_id, host=cs.host, port=cs.port, commstratobj=cs, throttlerin=self._throttlerin, throttlerout=self._throttlerout, cid_for_debugging=counterparty_id)
            cs.asyncsock = tcpc
        else:
            return # can't use this comm strat -- this problem will be discovered momentarily when someone tries to send a message  --Zooko 2000-09-26

        assert isinstance(tcpc, TCPConnection.TCPConnection)

        # debugprint("TCPCommsHandler._activate_commstrat(%s, %s): after activation\n", args=(counterparty_id, cs,), v=7, vs="commstrats")

        self._conncache.insert(counterparty_id, tcpc)
        assert len(self._conncache) > 0

    def _inmsg_handler(self, asyncsock, msg):
        """
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        @precondition `self._upward_inmsg_handler' must be callable.: callable(self._upward_inmsg_handler): "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."
        assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)

        # XXX How come this is sometimes `None'?  I think it should have been put in the cache
        # by a DoQ tasks launched from `handle_accept()', and that it can't be removed until after
        # `inmsg_handler()' has already run.  --Zooko 2001-05-18
        # Okay the answer is that in at least once case it was removed due to timeout, and then moments later
        # a message came in on it.  Currently removal takes quite a while to finalize -- as it has to go to the
        # asyncore thread and then back, so instead of trying to leave it in _conncache until it is finalized, I'm
        # just going to comment out this assertion.  --Zooko 2001-05-29
        # assert self._conncache.get(asyncsock._key) is asyncsock, "asyncsock: %s: asyncsock._key: %s, self._conncache.get(asyncsock._key): %s" % (hr(asyncsock), hr(asyncsock._key), hr(self._conncache.get(asyncsock._key)),)

        # Testing whether this is the only case that this happens.
        # assert (self._conncache.get(asyncsock._key) is asyncsock) or (asyncsock._closing), "asyncsock: %s: asyncsock._key: %s, self._conncache.get(asyncsock._key): %s" % (hr(asyncsock), hr(asyncsock._key), hr(self._conncache.get(asyncsock._key)),)
        if not ((self._conncache.get(asyncsock._key) is asyncsock) or (asyncsock._closing)):
            debugprint("faux AssertionFailure: (self._conncache.get(asyncsock._key) is asyncsock) or (asyncsock._closing) -- asyncsock: %s: asyncsock._key: %s, self._conncache.get(asyncsock._key): %s", args=(asyncsock, asyncsock._key, self._conncache.get(asyncsock._key),))
            
        cs = self._cid_to_cs.get(asyncsock._key)
        if (cs is not None) and (cs.asyncsock is asyncsock) and (self._conncache.get(asyncsock._key) is asyncsock) and (not asyncsock._closing):
            # If the current `cs' points to a useful (i.e. registered and non-closing) socket, then just recommend to keep the current cs.
            assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
            self._upward_inmsg_handler(msg, cs, asyncsock._key)
        elif not asyncsock._closing:
            # If `asyncsock' is a useful socket, recommend to use it.
            assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
            self._upward_inmsg_handler(msg, CommStrat.TCP(tcpch=self, broker_id=None, asyncsock=asyncsock), asyncsock._key)
        else:
            # There is no known useful socket.  Recommend nothing.
            assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
            self._upward_inmsg_handler(msg, None, None)

    def _close_handler(self, tcpc):
        self._conncache.remove_socket_if_present(tcpc)

    # The `handle_spam()' methods and the `_inmsg_handler()' are the "bottom" interface, to be called by the asyncore thread.  There can be (one) thread touching the bottom interface and (one) thread touching the top interface at the same time.
    def handle_accept(self) :
        try:
            thingie = self.accept()

            if not (((type(thingie) is types.TupleType) or (type(thingie) is types.ListType))):
                debugprint("got a non-sequence from `socket.accept()'.  Ignoring.  thingie: %s :: %s\n", args=(thingie, type(thingie),), v=0, vs="debug")
                return
        except socket.error, le:
            debugprint("got an exception from `socket.accept()'.  Ignoring.  le: %s\n", args=(le,), v=0, vs="debug")
            return

        (sock, addr) = thingie
        key = idlib.make_new_random_id(thingtype='TCPConnection')
        while hasattr(sock, 'socket'):
            # unwrap it from asyncore because we're about to wrap it in asyncore
            sock = sock.socket
        tcpc = TCPConnection.TCPConnection(inmsg_handler_func=self._inmsg_handler, close_handler_func=self._close_handler, key=key, sock=sock, throttlerin=self._throttlerin, throttlerout=self._throttlerout)
        pn = None
        try:
            pn = tcpc.getpeername()
        except:
            pass

        # debugprint("TCPCommsHandler: handle_accept(): the new socket %s has peername: %s and addr: %s\n", args=(sock, pn, addr), v=7, vs="commstrats")

        DoQ.doq.add_task(self._conncache.insert, args=(key, tcpc))

    def handle_write(self):
        debugprint("TCPCommsHandler: handle_write() called.  self: %s\n", args=(self,), v=0, vs="debug")
        return

    def handle_connect(self):
        debugprint("TCPCommsHandler: handle_connect() called.  self: %s\n", args=(self,), v=0, vs="debug")
        return

    def handle_read(self):
        # `handle_read()' gets called on Linux 2.4.0.  Oh well.  --Zooko 2001-01-20
        # debugprint("TCPCommsHandler: handle_read() called.  self: %s\n", args=(self,), v=0, vs="debug")
        return

    def handle_close(self):
        debugprint("TCPCommsHandler: handle_close() called.  self: %s\n", args=(self,), v=0, vs="debug")
        return

    def _throttle(self):
        self._throttled = 1 # `true'
        self.readable = self._readable_false

    def _unthrottle(self):
        self._throttled = None # `false'
        # Now if we are listening, then we are now ready to accept connections.
        if self._islistening:
            self.readable = self._readable_true

    def _readable_true(self):
        return 1 # `true'

    def _readable_false(self):
        return 0 # `false'

    def writable(self) :
        return 0   # this is a listening socket only, its never writable

    def log(self, message):
        # for faster operation, comment this whole method out and replace it with "def log(): return".  --Zooko 2000-12-11
        return
        # if message[-1:] == "\n":
        #     debugprint("TCPCommsHandler: asyncore log: " + message, v=7, vs="commstrats")
        # else:
        #     debugprint("TCPCommsHandler: asyncore log: " + message + "\n", v=7, vs="commstrats")


# XXX multithreading issues>  --Zooko 2001-10-04
class TCPConnCache(Cache.SimpleCache):
    """
    A cache object, which closes TCP connections when their time is up, which
    preserves TCP connections that are in active use, and which keeps a few connections around
    if it has been hinted that they will be useful in the future (and which throws out the least
    frequently used when it needs to throw some out).
    """
    def __init__(self, cid_to_cs={}):
        """
        The following "virtual parameters" are pulled out of confman whenever they are referenced:
        @param TCP_MAINTAINED_CONNECTIONS the number of connections which have "probably will be
            used again someday" hints to keep open, or `-1' if all of them should be kept open
        @param TCP_MAX_CONNECTIONS the maximum number of conns to keep open (this is the
            absolute max, a `-1' in `TCP_MAINTAINED_CONNECTIONS' notwithstanding)
        @param TCP_TIMEOUT the number of seconds to give a connection even if we have no hint to
            keep it
        @param cid_to_cs a dict mapping cids to CommStrats; We look in the CommStrats to get
            hints.  We never change this dict.
        """
        Cache.SimpleCache.__init__(self)
        self._timelastcleaned = 0
        self._nice_cleanup_result = true
        self._cid_to_cs = cid_to_cs

    def remove_socket_if_present(self, tcpc, default=None):
        """
        @precondition `tcpc' must not be None.: tcpc is not None
        """
        assert tcpc is not None, "precondition: `tcpc' must not be None."

        curtcpc = self.get(tcpc._key)
        if curtcpc is tcpc:
            self.remove(tcpc._key)
            return tcpc
        else:
            return default

    def remove_if_present(self, key, default=None):
        if not self.has_key(key):
            return default

        tcpc = Cache.SimpleCache.remove(self, key)
        pn = None
        try:
            pn = tcpc.getpeername()
        except:
            pass

        # debugprint("TCPCommsHandler.TCPConnCache.remove(): key: %s, val: %s, val._cid_for_debugging: %s, val.getpeername(): %s\n", args=(key, tcpc, tcpc._cid_for_debugging, pn), v=8, vs="commstrats")
        if tcpc:
            tcpc.close(reason="remove_if_present()")
        else:
            debugprint("TCPCommsHandler.TCPConnCache.remove(): WARNING: didn't find any conn for cid %s\n", args=(key,), v=1, vs="ERROR")
        return tcpc

    def remove(self, key):
        """
        Over-riding SimpleCache's `remove()' to catch all things being removed from this cache.

        Remove the connection and call `close()' on it.
        """
        tcpc = Cache.SimpleCache.remove(self, key)
        pn = None
        try:
            pn = tcpc.getpeername()
        except:
            pass

        # debugprint("TCPCommsHandler.TCPConnCache.remove(): key: %s, val: %s, val._cid_for_debugging: %s, val.getpeername(): %s\n", args=(key, tcpc, tcpc._cid_for_debugging, pn), v=8, vs="commstrats")
        if tcpc:
            tcpc.close(reason="remove()")
        else:
            debugprint("TCPCommsHandler.TCPConnCache.remove(): WARNING: didn't find any conn for cid %s\n", args=(key,), v=1, vs="ERROR")
        return tcpc

    def insert(self, key, item):
        """
        Over-riding SimpleCache's `insert()' to catch all things being inserted into this cache.

        If the cache is near maximum size, then this calls `_cleanup()' before inserting.

        @precondition `item' must be a TCPConnection.: isinstance(item, TCPConnection.TCPConnection): "item: %s :: %s" % (hr(item), hr(type(item)))
        """
        assert isinstance(item, TCPConnection.TCPConnection), "precondition: `item' must be a TCPConnection." + " -- " + "item: %s :: %s" % (hr(item), hr(type(item)))

        # If this item is already in the cache under this key, we're done.
        if self.get(key) is item:
            return

        # If this item is already in the cache under an old key, then remove it from there...
        if item._key:
            if self.get(item._key) is item:
                Cache.SimpleCache.remove(self, item._key)

        # Set the new key.
        item._key = key

        # If there is a different item under this key already, then remove it:
        if self.has_key(key):
            self.remove(key)

        if len(self._dict) > (int(confman.get('TCP_MAX_CONNECTIONS', 50)) - 1):
            if not self._cleanup(int(confman.get('TCP_MAX_CONNECTIONS', 50)) - 1):
                raise CommsError.CannotSendError, "too many busy connections"

        return Cache.SimpleCache.insert(self, key, item)

    def _cleanup(self, maxconns):
        """
        @returns "success" -- `true' if and only if it pared down to less than or equal to
            `maxconns' connections;  The only time it can fail is if there are more than `max'
            connections that are currently busy (they all return `true' from
            `TCPConnection.is_busy()').

        XXX Note: this might be a slow method when there are many (?? how many?) connections
        because it does a lot of sorting in order to choose the very best connections to keep.
        This could probably be sped-up but it probably wouldn't be a win since N is normally so
        low. In fact, one solution if this turns out to be slow when there are many connections
        is just to turn down TCP_MAX_CONNECTIONS to be small enough that this is fast!  :-)
        --Zooko 2000-08-15

        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."

        def cmpmaybs(tupa, tupb, self=self):
            (ka, tcpa) = tupa
            (kb, tcpb) = tupb
            return -1 * cmp(tcpa._inmsgs, tcpb._inmsgs)

        def cmpprobs(tupa, tupb, self=self):
            tcp_timeout = int(confman.get('TCP_TIMEOUT', 60))
            (ka, tcpa) = tupa
            (kb, tcpb) = tupb
            if tcpa.is_busy(tcp_timeout):
                if tcpb.is_busy(tcp_timeout):
                    # Both are in the middle of something.
                    return -1 * cmp(tcpa._last_io_time, tcpb._last_io_time) # highest (most recent) io_time first
                else:
                    # tcpa is in the middle of something so it goes first.
                    return -1
            else:
                if tcpb.is_busy(tcp_timeout):
                    # tcpb is in the middle of something so it goes first.
                    return 1

            # Neither are in the middle of something.
            return -1 * cmp(tcpa._last_io_time, tcpb._last_io_time) # highest (most recent) io_time first

        try:
            # debugprint("TCPConnCache._cleanup(): starting... self: %s, MAINT: %s, MAX: %s, len(self): %s\n", args=(self, confman.get('TCP_MAINTAINED_CONNECTIONS', '5'), confman.get('TCP_MAX_CONNECTIONS', '50'), len(self)), v=6, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11

            now = time.time()

            # "maintain" connections, sorted with most frequently used first;  This list never
            # exceeds nummaintainedconns, and it is the first to go if we approach maxconns.
            listomaybes = []
            # busy and "expect response" connections, sorted so that the best bets are first;
            # This list never exceeds maxconns.
            listoprobablies = []

            def addtomaybes(k, tcpc, self=self, listomaybes=listomaybes, listoprobablies=listoprobablies, cmpmaybs=cmpmaybs, maxconns=maxconns):
                listomaybes.append((k, tcpc))
                # Sort the maybes with the most-used at the front of the list.
                listomaybes.sort(cmpmaybs)
                # If adding this put us over the limit...
                # We can have only this many maybes:
                cutoff = min(long(confman.get('TCP_MAINTAINED_CONNECTIONS', '5')), maxconns - len(listoprobablies))
                if (cutoff >= 0) and (len(listomaybes) > cutoff):
                    assert (cutoff + 1) == len(listomaybes), "internal error -- the listomaybes should be checked at each insert and never allowed to grow over limit."
                    (k, tcpc) = listomaybes.pop(cutoff)
                    assert cutoff == len(listomaybes)
                    pn = None
                    try:
                        pn = tcpc.getpeername()
                    except:
                        pass

                    if cutoff == (maxconns - len(listoprobablies)):
                        debugprint("TCPConnCache._cleanup(): removing connection %s _cid_for_debugging: %s, .getpeername(): %s, which I 'maybe' wanted due to too many total connections.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
                    else:
                        debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, which I 'maybe' wanted due to too many maintained connections.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
                    self.remove(k)

            def addtoprobablies(k, tcpc, self=self, listomaybes=listomaybes, listoprobablies=listoprobablies, cmpprobs=cmpprobs, maxconns=maxconns):
                listoprobablies.append((k, tcpc))
                # Sort the probablies with the best at the front of the list.
                # First: active connections with half-finished messages and recent activity,
                # sorted with most recent network activity first.
                # Second: "expect response" connections sorted with most-frequently-used first.
                listoprobablies.sort(cmpprobs)
                # We can only have this many probablies:
                cutoff = maxconns
                if (cutoff >= 0) and (len(listoprobablies) > cutoff):
                    assert (cutoff + 1) == len(listoprobablies), "internal error -- the listoprobablies should be checked at each insert and never allowed to grow over limit."
                    (k, tcpc) = listoprobablies.pop(cutoff)
                    assert cutoff == len(listoprobablies)
                    # If we are about to kill a busy connection then don't do it and instead return `false'.
                    if tcpc.is_busy(long(confman.get('TCP_TIMEOUT', '60'))):
                        return false # failure
                    pn = None
                    try:
                        pn = tcpc.getpeername()
                    except:
                        pass

                    debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, which I 'probably' wanted due to too many total connections.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=3, vs="comm hints")
                    self.remove(k)

                # We can only have this many maybes:
                cutoff = min(long(confman.get('TCP_MAINTAINED_CONNECTIONS', '5')), maxconns - len(listoprobablies))
                if (cutoff >= 0) and (len(listomaybes) > cutoff):
                    assert (cutoff + 1) == len(listomaybes), "internal error -- the listomaybes should be checked at each insert and never allowed to grow over limit."
                    (k, tcpc) = listomaybes.pop(cutoff)
                    assert cutoff == len(listomaybes)
                    pn = None
                    try:
                        pn = tcpc.getpeername()
                    except:
                        pass

                    debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, due to too many maintained connections.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
                    self.remove(k)


            for (k, tcpc) in self._dict.items():
                pn = None
                try:
                    pn = tcpc.getpeername()
                except:
                    pass

                cs = self._cid_to_cs.get(k)
                if cs:
                    hint = cs.hint

                    # debugprint("TCPConnCache._cleanup(): examining connection %s._cid_for_debugging: %s, .getpeername(): %s -- hint: %s, hintnumexpectedresponses: %s, hintnumexpectedsends: %s.\n", args=(tcpc, tcpc._cid_for_debugging, pn, hint, cs.hintnumexpectedresponses, cs.hintnumexpectedsends), v=7, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11
                else:
                    hint = HINT_NO_HINT   # we didn't have a CommStrat for k, no hint available

                # Remove it if it is closing.
                if tcpc._closing:
                    # debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, because it has been closed.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=6, vs="comm hints")
                    self.remove(k)
                    continue

                # Leave it alone if it is busy.
                if tcpc.is_busy(long(confman.get('TCP_TIMEOUT', '60'))):
                    # debugprint("TCPConnCache._cleanup(): keeping connection %s._cid_for_debugging: %s, .getpeername(): %s probably: it is busy.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=7, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11

                    addtoprobablies(k, tcpc)
                    continue

                if (hint & HINT_EXPECT_RESPONSE) or (hint & HINT_EXPECT_TO_RESPOND):
                    # We're waiting for a response.  This one is a definite keeper.
                    # debugprint("TCPConnCache._cleanup(): keeping connection %s._cid_for_debugging: %s, .getpeername(): %s probably: waiting for response.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=7, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11

                    addtoprobablies(k, tcpc)
                    continue
                if hint & HINT_EXPECT_NO_MORE_COMMS:
                    # loser
                    debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, due to HINT_EXPECT_NO_MORE_COMMS.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
                    self.remove(k)
                    continue
                if hint & HINT_EXPECT_MORE_TRANSACTIONS:
                    # debugprint("TCPConnCache._cleanup(): keeping connection %s._cid_for_debugging: %s, .getpeername(): %s maybe: expect more transactions.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=7, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11
                    addtomaybes(k, tcpc)
                    continue

                # If we have no better clue to go on, then just time it out if it is old.
                if tcpc.is_idle(long(confman.get('TCP_TIMEOUT', '60'))):
                    debugprint("TCPConnCache._cleanup(): removing connection %s._cid_for_debugging: %s, .getpeername(): %s, due to idleness.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=5, vs="comm hints")
                    self.remove(k)
                else:
                    # debugprint("TCPConnCache._cleanup(): keeping connection %s._cid_for_debugging: %s, .getpeername(): %s maybe: it isn't idle.\n", args=(tcpc, tcpc._cid_for_debugging, pn), v=8, vs="comm hints") ### for faster operation, comment this line out.  --Zooko 2000-12-11
                    pass

                    addtomaybes(k, tcpc)

            return true # success
        finally:
            self._timelastcleaned = time.time()
            # debugprint("TCPConnCache._cleanup(): finishing.  len(self): %s\n", args=(len(self),), v=7, vs="comm hints") ## verbose connection caching diags ### for faster operation, comment this line out.  --Zooko 2000-12-11

    def _cleanup_nice(self):
        """
        This is "nice" because it just returns if less than 5 seconds have elapsed since the
        last cleanup.
        """
        if (time.time() - self._timelastcleaned) < 5:
            return self._nice_cleanup_result

        self._nice_cleanup_result = self._cleanup(long(confman.get('TCP_MAX_CONNECTIONS', '50')))
        return self._nice_cleanup_result

# Generic stuff
NAME_OF_THIS_MODULE="TCPCommsHandler"

mojo_test_flag = 1

def run():
    confman['MAX_VERBOSITY'] = "9"
    import RunTests
    RunTests.runTests(NAME_OF_THIS_MODULE)

# #### this runs if you import this module by itself
# if __name__ == '__main__':
#     run()

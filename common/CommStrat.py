#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import exceptions
import time # actually just for debugging
import traceback # actually just for debugging
import types

# pyutil modules
from config import DEBUG_MODE
from debugprint import debugprint

# our modules
import DataTypes
import OurMessages
import idlib

# Mojo Nation modules
from CommHints import HINT_EXPECT_RESPONSE, HINT_EXPECT_MORE_TRANSACTIONS, HINT_EXPECT_NO_MORE_COMMS, HINT_NO_HINT
from DataTypes import UNIQUE_ID, ANY, ASCII_ARMORED_DATA, NON_NEGATIVE_INTEGER, MOD_VAL, INTEGER, ListMarker, OptionMarker
true = 1
false = 0
import MojoKey
import MojoMessage
import OurMessages
from OurMessagesCommStrat import *
import TCPConnection
from humanreadable import hr
import ipaddresslib
import mencode
import modval
import mojoutil
import string



class Error(exceptions.StandardError): pass
class UnsupportedTypeError(exceptions.StandardError): pass


"""
TCP(host, port, asyncsock) - a strategy for opening tcp connections or else using a currently open tcp socket

Relay(relay_server) - makes a strategy which routes through the given relay server

Crypto(pubkey, lowerstrategy) - a combination of a pub key and another strategy for transmitting ciphertext

Pickup() - if you have a message for this person, store it and she will contact you and pick it up;  Relay servers use a Pickup strategy to give messages to their clients currently.  (Not really -- they currently implement pickup behavior in RelayServerHandlers.py, but perhaps it would be cleaner if they used Pickup ?  --Zooko 2001-09-02)
"""

def is_reachable(cs):
    # Find the bottommost strategy...
    while hasattr(cs, "_lowerstrategy"):
        cs = cs._lowerstrategy

    if (cs) and ((isinstance(cs, TCP) and (ipaddresslib.is_routable(cs.host))) or (isinstance(cs, Relay))):
        return true
    else:
        return false

def choose_best_strategy(cs1, cs2):
    """
    You should pass the newer, or most recently "suggested" cs as `cs2'.  If there is a tie we will prefer that one.
    (But if they are the *same*, we will prefer the old one.  For example, if the two strategies both use the same
    crypto key and they each have an open TCP connection, then there is a *tie* in terms of which one is
    preferred, so we use the newly suggested one.  If two strategies both use the same crypto key and they both
    use the *same* open TCP connection, then they are the *same* and we keep using the current one.)

    @param cs1 an instance of CommStrat; Can be `None'.
    @param cs2 an instance of CommStrat; Can be `None'.

    @return a reference to whichever of `cs1' or `cs2' is most preferable
    """
    # If either one is `None' then we prefer the other.
    if cs1 is None:
        return cs2
    if cs2 is None:
        return cs1

    # If they are the same then we prefer the current one.
    if cs1.same(cs2):
        return cs1

    # We always prefer open TCP sockets over anything else...
    if (isinstance(cs1, TCP) and cs1.is_open_socket()) and not (isinstance(cs2, TCP) and cs2.is_open_socket()):
        return cs1
    if (isinstance(cs2, TCP) and cs2.is_open_socket()) and not (isinstance(cs1, TCP) and cs1.is_open_socket()):
        return cs2

    # If neither is an open TCP socket, or if both are open TCP sockets (== if control reaches this line), then we always prefer a newer sequence number over and older or a None:
    cs1seqno = cs1._commstratseqno
    if cs1seqno is None:
        cs1seqno = -1
    cs2seqno = cs2._commstratseqno
    if cs2seqno is None:
        cs1seqno = -1
    if cs1seqno > cs2seqno:
        return cs1
    elif cs2seqno > cs1seqno:
        return cs2

    # We always prefer TCP over non-TCP...
    if isinstance(cs1, TCP) and not isinstance(cs2, TCP):
        return cs1
    if isinstance(cs2, TCP) and not isinstance(cs1, TCP):
        return cs2

    if isinstance(cs1, TCP):
        # Note: if control reaches here then both strats are TCP.
        # Among non-same open sockets with tieing commstratseqno, we prefer the newer one (sort of arbitrary).
        if cs1.is_open_socket():
            # Note: if control reaches here then both strats are open TCP connections.
            return cs2

        # Among IP addresses, we definitely prefer routeable ones...
        if cs1.is_routeable() and not cs2.is_routeable():
            return cs1
        if cs2.is_routeable() and not cs1.is_routeable():
            return cs2

        # Among non-same, similarly-routeable IP addresses with tieing commstratseqno, we prefer the newer one (sort of arbitrary).
        return cs2

    # Note: if control reaches here then neither strat is a TCP.
    # We always prefer Relay over "none of the above":
    if isinstance(cs1, Relay) and not isinstance(cs2, Relay):
        return cs1
    if isinstance(cs2, Relay) and not isinstance(cs1, Relay):
        return cs2

    # Among non-same Relays with the same (or unknown) commstratseqno, we prefer the newer one (sort of arbitrary):
    # Note, it would be nice to check if we have an open TCP connection to one of the relay servers, and
    # if so prefer that Relay strat.  Also it might be nice to actually handicap the Relay servers here.
    return cs2

class CommStrat:
    def __init__(self, broker_id=None, commstratseqno=None):
        """
        @precondition `broker_id' must be `None' or an id.: (broker_id is None) or (idlib.is_sloppy_id(broker_id)): "broker_id: %s" % hr(broker_id)
        """
        assert (broker_id is None) or (idlib.is_sloppy_id(broker_id)), "precondition: `broker_id' must be `None' or an id." + " -- " + "broker_id: %s" % hr(broker_id)

        self.hint = HINT_NO_HINT
        self.hintnumexpectedresponses = 0
        self.hintnumexpectedsends = 0
        self._commstratseqno = commstratseqno
        self._broker_id = broker_id 

    def to_dict(self):
        d = {}
        if self._broker_id is not None:
            d['broker id'] = self._broker_id
        if self._commstratseqno is not None:
            d['comm strat sequence num'] = self._commstratseqno
        return d

    def get_id(self):
        return self._broker_id

    def is_useful(self):
        """@returns boolean indicating if this CommStrat has any reason to exist anymore"""
        return None   # if nothing overrides this, its not very useful...

class TCP(CommStrat):
    def __init__(self, tcpch, broker_id, host=None, port=None, asyncsock=None, commstratseqno=None):
        """
        @param tcpch the TCPCommsHandler
        @param asyncsock an instance of TCPConnection

        @precondition `asyncsock' must be an instance of TCPConnection or nothing.: (asyncsock is None) or isinstance(asyncsock, TCPConnection.TCPConnection): "asyncsock: %s :: %s" % (hr(asyncsock), hr(type(asyncsock)))
        @precondition `broker_id' must be a binary id or None.: (broker_id is None) or idlib.is_binary_id(broker_id): "broker_id: %s :: %s" % (hr(broker_id), hr(type(broker_id)),)
        """
        assert (asyncsock is None) or isinstance(asyncsock, TCPConnection.TCPConnection), "precondition: `asyncsock' must be an instance of TCPConnection or nothing." + " -- " + "asyncsock: %s :: %s" % (hr(asyncsock), hr(type(asyncsock)))
        assert (broker_id is None) or idlib.is_binary_id(broker_id), "precondition: `broker_id' must be a binary id or None." + " -- " + "broker_id: %s :: %s" % (hr(broker_id), hr(type(broker_id)),)

        CommStrat.__init__(self, broker_id, commstratseqno=commstratseqno)

        self._tcpch = tcpch
        self.host = host
        self.port = port
        self.asyncsock = asyncsock
   
    def __repr__(self):
        return '<%s to %s:%s via %s, %x>' % (self.__class__.__name__, self.host, self.port, self.asyncsock, id(self),)

    def send(self, msg, hint=HINT_NO_HINT, fast_fail_handler=None, timeout=None, commstratseqno=None):
        """
        @precondition `self._broker_id' must be an id.: idlib.is_binary_id(self._broker_id): "self._broker_id: %s :: %s" % (hr(self._broker_id), hr(type(self._broker_id)),)
        """
        assert idlib.is_binary_id(self._broker_id), "precondition: `self._broker_id' must be an id." + " -- " + "self._broker_id: %s :: %s" % (hr(self._broker_id), hr(type(self._broker_id)),)

        # debugprint("%s.send(): self._broker_id: %s\n", args=(self, self._broker_id,))
        self._tcpch.send_msg(self._broker_id, msg=msg, hint=hint, fast_fail_handler=fast_fail_handler)

    def is_routeable(self):
        return self.host and ipaddresslib.is_routable(self.host)

    def is_open_socket(self):
        return (self.asyncsock) and not self.asyncsock._closing

    def same(self, other):
        """
        Two TCP's are same iff they both have the same non-None socket object or if they both have None socket objects and the same host and port

        @return `true' iff `self' and `other' are actually the same strategy
        """
        if not hasattr(other, 'asyncsock'):
            assert hasattr(self, 'asyncsock')
            return false
        if self.asyncsock is not None:
            return self.asyncsock is other.asyncsock
        else:
            if other.asyncsock is not None:
                return false
        if not hasattr(other, 'host'):
            assert hasattr(self, 'host')
            return false
        if not hasattr(other, 'port'):
            assert hasattr(self, 'port')
            return false
        return (self.host == other.host) and (self.port == other.port)

    def to_dict(self):
        d = CommStrat.to_dict(self)

        d['comm strategy type'] = "TCP"

        if self.host:
            d['IP address'] = self.host

        if self.port:
            d['port number'] = `self.port`

        if self.asyncsock:
            d['open connection'] = 'true'
            
            try:
                peername = self.asyncsock.getpeername()
                d['open connection peername'] = `peername`
            except:
                pass

        return d

    def is_useful(self):
        return (self.asyncsock and not self.asyncsock._closing)

class Relay(CommStrat):
    def __init__(self, relayer_id, broker_id, mtm, commstratseqno=None):
        """
        @precondition `relayer_id' must be an id.: idlib.is_sloppy_id(relayer_id): "relayer_id: %s" % hr(relayer_id)
        """
        assert idlib.is_sloppy_id(relayer_id), "precondition: `relayer_id' must be an id." + " -- " + "relayer_id: %s" % hr(relayer_id)

        CommStrat.__init__(self, broker_id, commstratseqno=commstratseqno)

        self._relayer_id = relayer_id
        self._mtm = mtm
        self._been_used = 0   # flag indicating if this CommStrat has been used to process at least one message

        if DEBUG_MODE:
            self.debcr = traceback.extract_stack()

    def __repr__(self):
        return '<%s to %s via %s at %x>' % (self.__class__.__name__, hr(self._broker_id), hr(self._relayer_id), id(self))

    def same(self, other):
        """
        Two Relay's are same iff they have the same `_relayer_id'.

        @return `true' iff `self' and `other' are actually the same strategy
        """
        if not hasattr(other, '_relayer_id'):
            assert hasattr(self, '_relayer_id')
            return false
        return idlib.equal(self._relayer_id, other._relayer_id)

    def to_dict(self):
        d = CommStrat.to_dict(self)
        d['comm strategy type'] = "relay" # XXXX This should be changed to "Relay" to match the name of the class.  --Zooko 2000-08-02
        d['relayer id'] = self._relayer_id
        return d

    def is_useful(self):
        return not self._been_used

    def send(self, msg, hint=HINT_NO_HINT, fast_fail_handler=None, timeout=None, commstratseqno=None):
        """
        @param commstratseqno This relay comm strat must have a comm strat sequence num strictly greater than `commstratseqno';  If `None', then that means this is being initiated by the local higher level user, or it is a "pass this along" from an old broker that does not send commstratseqno with its "pass this along"'s.  If it is `None', then you send it.
        """
        timeout = long(timeout)

        if idlib.equal(self._relayer_id, self._mtm.get_id()):
            fast_fail_handler(failure_reason="aborting a recursive `pass this along' to myself")
            return

        if idlib.equal(self._relayer_id, self._broker_id):
            debugprint("Warning: we have gotten the idea that the comm strat for sending messages to %s is to relay through herself!  CommStrat.Relay: %s\n", args=(self._broker_id, self,), v=2, vs="debug")
            fast_fail_handler(failure_reason="aborting a recursive `pass this along' to %s via herself" % hr(self._relayer_id,))
            return

        # debugprint("commstratseqno: %s, self._commstratseqno: %s\n", args=(commstratseqno, self._commstratseqno,))
        if (commstratseqno is not None) and ((self._commstratseqno is None) or (commstratseqno >= self._commstratseqno)):
            # This message is not guaranteed to terminate -- it could form a remailing loop -- dump it.
            fast_fail_handler(failure_reason="aborting a non-guaranteed-termination relay; commstratseqno: %s, self._commstratseqno: %s" % (hr(commstratseqno),  hr(self._commstratseqno),))
            return

        if DEBUG_MODE:
            assert self._mtm is not None, "self: %s, self.debcr: %s" % (hr(self), hr(self.debcr))
        else:
            assert self._mtm is not None, "self: %s" % hr(self)

        wrappermsgbody = { 'recipient': idlib.to_mojosixbit(self._broker_id), 'message': msg }
        if self._commstratseqno is not None:
            wrappermsgbody['comm strat sequence num'] = self._commstratseqno
        else:
            wrappermsgbody['comm strat sequence num'] = -1

        def outcome_func_from_pass_this_along(widget, outcome, failure_reason=None, self=self, msg=msg):
            assert idlib.equal(widget.get_counterparty_id(), self._relayer_id)
            # debugprint("CommStrat.Relay: Got result of `pass this along'.  self._relayer_id: %s, widget: %s, outcome: %s, failure_reason: %s\n", args=(self._relayer_id, widget, outcome, failure_reason,), v=3, vs="commstrats")
            if failure_reason:
                self._mtm.forget_comm_strategy(self._broker_id, idlib.make_id(msg, 'msg'), outcome=outcome, failure_reason="couldn't contact relay server: %s" % hr(outcome))
            if (not failure_reason) and (outcome.get('result') != "ok") and (outcome.get('result') != "success"):
                # Note: `ok' is for backwards compatibility, `success' is preferred.
                self._mtm.forget_comm_strategy(self._broker_id, idlib.make_id(msg, 'msg'), outcome=outcome, failure_reason="got failure from relay server: %s" % hr(outcome))

        # debugprint("CommStrat.Relay: Initiating `pass this along'...  self._relayer_id: %s\n", args=(self._relayer_id,), v=3, vs="commstrats")

        self._mtm.initiate(self._relayer_id, 'pass this along v2', wrappermsgbody, outcome_func=outcome_func_from_pass_this_along, post_timeout_outcome_func=outcome_func_from_pass_this_along, commstratseqno=self._commstratseqno)
        self._been_used = 1

class Crypto(CommStrat):
    def __init__(self, pubkey, lowerstrategy, broker_id=None):
        """
        @param lowerstrategy the lower-level comms strategy, either given by meta-tracking or
            suggested by the way that the last message arrived (e.g. For TCP, the suggested
            strategy is to send a message back down the connection over which the last message
            arrived.)

        @precondition `pubkey' must be a well-formed MojoKey.: MojoKey.publicKeyForCommunicationSecurityIsWellFormed(pubkey)
        @precondition `lowerstrategy' must be a CommStrat.: isinstance(lowerstrategy, CommStrat): "lowerstrategy: %s" % hr(lowerstrategy)
        @precondition `broker_id' must be the id of `pubkey', or else it must be `None'.: (broker_id is None) or (idlib.equal(idlib.make_id(pubkey, 'broker'), broker_id)): "broker_id: %s" % hr(broker_id)
        """
        assert MojoKey.publicKeyForCommunicationSecurityIsWellFormed(pubkey), "precondition: `pubkey' must be a well-formed MojoKey."
        assert isinstance(lowerstrategy, CommStrat), "precondition: `lowerstrategy' must be a CommStrat." + " -- " + "lowerstrategy: %s" % hr(lowerstrategy)
        assert (broker_id is None) or (idlib.equal(idlib.make_id(pubkey, 'broker'), broker_id)), "precondition: `broker_id' must be the id of `pubkey', or else it must be `None'." + " -- " + "broker_id: %s" % hr(broker_id)

        CommStrat.__init__(self, idlib.make_id(pubkey, 'broker'))

        self._pubkey = pubkey
        self._lowerstrategy = lowerstrategy

    def __repr__(self):
        return '<%s pubkey_id %s at %x, lowerstrategy: %s>' % (self.__class__.__name__, idlib.to_ascii(idlib.make_id(self._pubkey)), id(self), self._lowerstrategy)

    def same(self, other):
        """
        Two Crypto's are same iff they have the same pub key and their lowerstrategies are same.

        @return `true' iff `self' and `other' are actually the same strategy
        """
        # debugprint("%s.same(%s); stack: %s\n", args=(self, other, traceback.extract_stack(),))
        if not hasattr(other, '_pubkey'):
            assert hasattr(self, '_pubkey')
            return false
        if self._pubkey != other._pubkey:
            return false
        assert hasattr(self, '_lowerstrategy')
        if not hasattr(other, '_lowerstrategy'):
            return false
        return self._lowerstrategy.same(other._lowerstrategy)

    def to_dict(self):
        d = CommStrat.to_dict(self)
        d['comm strategy type'] = "crypto" # XXXX This should be changed to "Crypto" to match the name of the class.  --Zooko 2000-08-02
        d['pubkey'] = mencode.mdecode(self._pubkey)
        d['lowerstrategy'] = self._lowerstrategy.to_dict()
        return d

    def is_useful(self):
        # Crypto commstrats by themselves are only as useful as their lowerstrategy that actually sends the data
        return (self._lowerstrategy and self._lowerstrategy.is_useful())


class Pickup(CommStrat):
    def __init__(self, broker_id=None, commstratseqno=None):
        CommStrat.__init__(self, broker_id, commstratseqno=commstratseqno)
        return

    def to_dict(self):
        d = CommStrat.to_dict(self)
        d['comm strategy type'] = "pickup" # XXXX This should be changed to "Pickup" to match the name of the class.  --Zooko 2000-08-02
        return d

    def same(self, other):
        """
        Two Pickup's are always the same.

        @return `true' iff `self' and `other' are actually the same strategy
        """
        return isinstance(other, Pickup)

def dict_to_type(dict):
    return dict['comm strategy type']

def crypto_dict_to_pub_key(dict):
    return mencode.mencode(dict['pubkey'])

def crypto_dict_to_id(dict):
    """
    @precondition `dict' must be a dict.: type(dict) is types.DictType: "dict: %s :: %s" % (hr(dict), hr(type(dict)),)
    """
    assert type(dict) is types.DictType, "precondition: `dict' must be a dict." + " -- " + "dict: %s :: %s" % (hr(dict), hr(type(dict)),)

    return idlib.make_id(mencode.mencode(dict['pubkey']), 'broker')

def addr_to_id(addr):
    """
    @precondition `addr' must be a dict with a ["connection strategies"][0]["pubkey"] key chain, or else a CommStrat instance with a broker_id.: ((type(addr) is types.DictType) and (addr.has_key("connection strategies")) and (addr.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(addr) is types.InstanceType) and (isinstance(addr, CommStrat)) and (addr._broker_id is not None)): "addr: %s :: %s" % (hr(addr), hr(type(addr)),)
    """
    assert ((type(addr) is types.DictType) and (addr.has_key("connection strategies")) and (addr.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(addr) is types.InstanceType) and (isinstance(addr, CommStrat)) and (addr._broker_id is not None)), "precondition: `addr' must be a dict with a [\"connection strategies\"][0][\"pubkey\"] key chain, or else a CommStrat instance with a broker_id." + " -- " + "addr: %s :: %s" % (hr(addr), hr(type(addr)),)

    if type(addr) is types.DictType:
        return idlib.make_id(mencode.mencode(addr["connection strategies"][0]['pubkey']), 'broker')
    else:
        return addr.get_id()

def dict_to_strategy(dict, mtm, broker_id=None, commstratseqno=None):
    """
    @raises an UnsupportedTypeError if `dict' is not either a TCP, Relay, Crypto, or Pickup
    
    @precondition `broker_id' must be an id or None.: (broker_id is None) or (idlib.is_sloppy_id(broker_id)): "broker_id: %s :: %s" % (hr(broker_id), hr(type(broker_id)))
    """
    assert (broker_id is None) or (idlib.is_sloppy_id(broker_id)), "precondition: `broker_id' must be an id or None." + " -- " + "broker_id: %s :: %s" % (hr(broker_id), hr(type(broker_id)))

    if not ((dict.get('comm strategy type') == "TCP") or (dict.get('comm strategy type') == "relay") or (dict.get('comm strategy type') == "Relay") or (dict.get('comm strategy type') == "crypto") or (dict.get('comm strategy type') == "Crypto") or (dict.get('comm strategy type') == "pickup")) or (dict.get('comm strategy type') == "Pickup"):
        raise UnsupportedTypeError, "`dict' must be either a TCP, Relay, Crypto or Pickup." + " -- " + "dict: [%s]" % hr(dict)

    MojoMessage.checkTemplate(dict, COMM_STRAT_TEMPL)

    dictbroker_id = dict.get('broker id')
    if (broker_id is not None) and (dictbroker_id is not None):
        assert idlib.equal(broker_id, dictbroker_id)
    if broker_id is None:
        broker_id = dictbroker_id

    if dict.get('comm strat sequence num') is not None:
        commstratseqno = dict.get('comm strat sequence num')

    cst = dict['comm strategy type']
    if cst == "TCP":
        MojoMessage.checkTemplate(dict, TCP_COMM_STRAT_TEMPL)
        return TCP(mtm._ch._tcpch, broker_id, host=dict['IP address'], port=int(dict['port number']), commstratseqno=commstratseqno)

    if (cst == "Relay") or (cst == "relay"):
        MojoMessage.checkTemplate(dict, RELAY_COMM_STRAT_TEMPL)
        return Relay(relayer_id=dict['relayer id'], mtm=mtm, broker_id=broker_id, commstratseqno=commstratseqno)

    if (cst == "Pickup") or (cst == "pickup"):
        MojoMessage.checkTemplate(dict, PICKUP_COMM_STRAT_TEMPL)
        return Pickup(broker_id=broker_id, commstratseqno=commstratseqno)

    if (cst == "Crypto") or (cst == "crypto"):
        MojoMessage.checkTemplate(dict, CRYPTO_COMM_STRAT_TEMPL)
        return Crypto(mencode.mencode(dict['pubkey']), dict_to_strategy(dict['lowerstrategy'], broker_id=broker_id, mtm=mtm, commstratseqno=commstratseqno), broker_id=broker_id)

    raise Error, "Unknown strategy %s." % `cst`


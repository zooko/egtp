#!/usr/bin/env python #
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: CryptoCommsHandler.py,v 1.3 2002/02/11 14:47:57 zooko Exp $'

# standard modules
import traceback
import types
import sha
import string
import zlib

# pyutil modules
from config import DEBUG_MODE, REALLY_SLOW_DEBUG_MODE
from debugprint import debugprint

# our modules
import Cache
import CommsError
import CommStrat
from CommHints import HINT_EXPECT_RESPONSE, HINT_EXPECT_MORE_TRANSACTIONS, HINT_EXPECT_NO_MORE_COMMS, HINT_EXPECT_TO_RESPOND, HINT_THIS_IS_A_RESPONSE, HINT_NO_HINT
import DoQ
import MojoKey
import confutils
import humanreadable
import idlib
import mesgen
import mojosixbit
import mojoutil

true = 1
false = None


# Things to test:
# * Opens TCP connection, sends message, keeps TCP connection, receives reply.
# * Sends via relay.
# * Receives via relay.
# * Someone opens TCP connection to you, sends message, you keep TCP connection, send reply.
# * Someone opens TCP connection, never sends message, you keep it for awhile, but clean it when

#     the total conns > TCP_MAX_CONNECTIONS.
# * You are operating behind relay.  Someone sends you a message, you have phonebook entry from
#     them (either from them or from MT), and you know their comm strat is TCP, you open a TCP
#     connection to them and send reply.
# * They are operating behind relay.  You send them a message via relay.  They open a TCP
#     connection to you and send reply.  Next time you want to talk to them, you use the open
#     TCP connection.
# * You have an open TCP connection to a counterparty, which is working.  You get a new comm
#     strat from somewhere that says to use relay.  You ignore it and keep using the working TCP
#     connection.
# * You have an IP addr and port number for a counterparty.  You get a new comm strat from
#     somewhere that says to use relay.  You ignore it and try to open a connection using the IP
#     addr.
# * You are talking via TCP, and the connection dies.  You then learn from a MT that the
#     counterparty is available via relay.  You start using relay.

# messages who's cleartext is larger than this will be dropped
MAX_CLEARTEXT_LEN = 4*1024*1024  # 4megs is #)^*!)^& huge for a single message!

class CryptoCommsHandler:

    # This is -not- a descendent of BaseCommsHandler, we're moving away from the overly complex heirarchy and just
    # defining an interface that CommsHandler objects must support.

    def __init__(self, mesgen, tcpch):
        """
        @param mesgen the crypto object
        """
        self._mesgen = mesgen
        self._tcpch = tcpch
        # map cid to instance of CommStrat
        self._cid_to_cs = {}
 
    def shutdown(self):
        if hasattr(self, '_cid_to_cs'):
            del self._cid_to_cs
        if hasattr(self, '_mesgen'):
            del self._mesgen

    def stop_listening(self):
        # Err..  Ok.
        return

    def is_listening(self):
        return true

    def start_listening(self, inmsg_handler_func):
        """
        Start trying to get incoming messages which you will then pass to `inmsg_handler_func()'.

        @param inmsg_handler_func the function to be called whenever a message for us comes in
        """
        self._upward_inmsg_handler = inmsg_handler_func

    def send_msg(self, counterparty_id, msg, fast_fail_handler, hint=HINT_NO_HINT, timeout=None, commstratseqno=None):
        """
        @param commstratseqno the sequence number of the comm strat which has already
            been tried;  If you attempt a recursive delivery mechanism (relay), then you can
            avoid loops by ensuring that the next comm strategy you try has seqno > than
            this one.

        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        @precondition `msg' must be a string.: type(msg) == types.StringType
        """
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        assert type(msg) == types.StringType, "precondition: `msg' must be a string."
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        assert type(msg) == types.StringType, "precondition: `msg' must be a string."

        # debugprint("CryptoCommsHandler.send_msg()\n")
        if idlib.equal(counterparty_id, self.get_id()):
            DoQ.doq.add_task(self._upward_inmsg_handler, args=(counterparty_id, msg, None))
        else:
            try:
                cs = self._cid_to_cs.get(counterparty_id)
                if not cs:
                    fast_fail_handler(msgId=idlib.make_id(msg, 'msg'), failure_reason="no CommStrat.Crypto for this counterparty")
                    return

                llstrat = cs._lowerstrategy
                if not llstrat:
                    fast_fail_handler(msgId=idlib.make_id(msg, 'msg'), failure_reason="no llstrat for this counterparty")
                    return
                assert idlib.equal(llstrat._broker_id, counterparty_id), "counterparty_id: %s, cs: %s, llstrat: %s, llstrat._broker_id: %s" % (humanreadable.hr(counterparty_id), humanreadable.hr(cs), humanreadable.hr(llstrat), humanreadable.hr(llstrat._broker_id),)

                if not hasattr(llstrat, 'send'):
                    fast_fail_handler(msgId=idlib.make_id(msg, 'msg'), failure_reason="CommStrat lacks a `send()' method.: %s" % humanreadable.hr(llstrat))
                    return

                if len(msg) > MAX_CLEARTEXT_LEN :
                    raise CommsError.CannotSendError, "message too long: %s bytes" % len(msg)

                origmsglen = len(msg)
                try:
                    msg = zlib.compress(msg, 3)
                    debugprint("CryptoCommsHandler.send_msg(): sending compressed msg (%s bytes, orig %s)\n", args=(len(msg), origmsglen), v=14, vs="crypto")
                except zlib.error, e:
                    debugprint("CryptoCommsHandler.send_msg(): got `%s' during compression (%s bytes)\n", args=(e, origmsglen), v=5, vs="crypto") # verbose
                cyphertext = self._mesgen.generate_message(recipient_id = counterparty_id, message = msg)
                del msg  # we're done with it, encourage faster gc
            except mesgen.NoCounterpartyInfo, le:
                raise CommsError.CannotSendError, ("no counterparty public key", le)

            llstrat.send(msg=cyphertext, hint=hint, fast_fail_handler=fast_fail_handler, timeout=timeout, commstratseqno=commstratseqno)

    def inmsg_handler(self, msg, lowerstrategy, strategy_id_for_debug):
        """
        Processes an incoming message.

        @param lowerstrategy a comm strategy which is suggested by the caller;  Currently if the caller is a TCP comms handler, then this is a strategy for using the extant TCP connection, upon which `msg' arrived, to send further messages to the counterparty.  If the caller is a Relay comms handler, then this is `None'.  TODO: make it so that you consider using the same relay server to send back
        @param strategy_id_for_debug is a unique identifier which the *lower-level* comms handler uses to identify `lowerstrategy';  This is only used for diagnostic output.  Currently if the lower-level comms is TCP, and we don't yet know a public key which has signed messages that were sent over this TCP connection, then it is a random id, else it is the id of the public key which has signed messages that were sent over this TCP connection.  If the lower-level comms is Relay, then this is `None'.

        @precondition `msg' must be a string.: type(msg) == types.StringType: "msg: %s :: %s" % (humanreadable.hr(msg), humanreadable.hr(type(msg)))
        @precondition `strategy_id_for_debug' must be None if and only if `lowerstrategy' is None.: (strategy_id_for_debug is None) == (lowerstrategy is None): "strategy_id_for_debug: %s, lowerstrategy: %s" % (humanreadable.hr(strategy_id_for_debug), humanreadable.hr(lowerstrategy))
        """
        assert type(msg) == types.StringType, "precondition: `msg' must be a string." + " -- " + "msg: %s :: %s" % (humanreadable.hr(msg), humanreadable.hr(type(msg)))
        assert (strategy_id_for_debug is None) == (lowerstrategy is None), "precondition: `strategy_id_for_debug' must be None if and only if `lowerstrategy' is None." + " -- " + "strategy_id_for_debug: %s, lowerstrategy: %s" % (humanreadable.hr(strategy_id_for_debug), humanreadable.hr(lowerstrategy))

        try:
            counterparty_pub_key, cleartext = self._mesgen.parse(msg)
        except mesgen.Error, e:
            if isinstance(e, mesgen.SessionInvalidated):
                debugprint("%s.inmsg_handler(msg: %s, lowerstrategy: %s, strategy_id_for_debug: %s) got exceptions: %s\n", args=(self, msg, lowerstrategy, strategy_id_for_debug, e,), v=3, vs="crypto")
                return

            if lowerstrategy:
                if hasattr(lowerstrategy, 'asyncsock'):
                    if config.REALLY_SLOW_DEBUG_MODE:
                        debugprint("WARNING: a message arrived with suggested lowerstrategy %s, asyncsock: %s, strategy_id_for_debug: %s, that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s, traceback: %s\n", args= (lowerstrategy.to_dict(), lowerstrategy.asyncsock, strategy_id_for_debug, msg, e, traceback.extract_stack(),), v=1, vs="crypto")
                    else:
                        debugprint("WARNING: a message arrived with suggested lowerstrategy %s, asyncsock: %s, strategy_id_for_debug: %s, that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s\n", args= (lowerstrategy.to_dict(), lowerstrategy.asyncsock, strategy_id_for_debug, msg, e), v=1, vs="crypto")
                else:
                    if config.REALLY_SLOW_DEBUG_MODE:
                        debugprint("WARNING: a message arrived with suggested lowerstrategy %s, strategy_id_for_debug: %s, that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s, traceback: %s\n", args=(lowerstrategy.to_dict(), strategy_id_for_debug, msg, e, traceback.extract_stack(),), v=1, vs="crypto")
                    else:
                        debugprint("WARNING: a message arrived with suggested lowerstrategy %s, strategy_id_for_debug: %s, that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s\n", args=(lowerstrategy.to_dict(), strategy_id_for_debug, msg, e), v=1, vs="crypto")
            else:
                if config.REALLY_SLOW_DEBUG_MODE:
                    debugprint("WARNING: a message arrived with suggested strategy_id_for_debug %s that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s, traceback: %s\n", args=(strategy_id_for_debug, msg, e, traceback.extract_stack(),), v=1, vs="crypto")
                else:
                    debugprint("WARNING: a message arrived with suggested strategy_id_for_debug %s that couldn't be decrypted.  Perhaps it was cleartext, or garbled.  The message was %s.  The error was: %s\n", args=(strategy_id_for_debug, msg, e), v=1, vs="crypto")

            # if it is an UnknownSession error, attempt to send a note back down the lowerstrategy if it happens to be a two way connection
            if isinstance(e, mesgen.UnknownSession) and lowerstrategy:
                # XXX if all CommStrats are updated in the future to have a send() method, just use it if the CommStrat has a "twowaycomms" flag?
                if isinstance(lowerstrategy, CommStrat.TCP) and lowerstrategy.asyncsock:
                    debugprint("sending an 'invalidate session' note back on the TCP connection\n", v=1, vs="CryptoCommsHandler")
                    # send e.invalidate_session_msg back out this TCP Connection
                    lowerstrategy.asyncsock.send(e.invalidate_session_msg)
                else:
                    debugprint("message did not come via a two way CommStrat, cannot send an 'invalidate session'\n", v=3, vs="CryptoCommsHandler")

            return # drop it on the floor

        counterparty_id = idlib.string_to_id(counterparty_pub_key)

        assert MojoKey.publicRSAKeyForCommunicationSecurityIsWellFormed(counterparty_pub_key), "postcondition of `mesgen.parse()': `counterparty_pub_key' is a public key." + " -- " + "counterparty_pub_key: %s" % humanreadable.hr(counterparty_pub_key)

        if len(cleartext) > MAX_CLEARTEXT_LEN :
            debugprint("msg from %s dropped due to length: %s\n", args=(counterparty_id, len(cleartext)), v=0, vs="ERROR")
            return
        try:
            decomptext = mojoutil.safe_zlib_decompress_to_retval(cleartext, maxlen=MAX_CLEARTEXT_LEN)
        except (mojoutil.UnsafeDecompressError, mojoutil.TooBigError), le:
            debugprint("msg from %s dropped. le: %s\n", args=(counterparty_id, le), v=0, vs="ERROR")
            return
        except mojoutil.ZlibError, le:
            debugprint("msg from %s not zlib encoded. processing it anyway for backwards compatibility. le: %s\n", args=(counterparty_id, le,), v=3, vs="debug")
            decomptext = cleartext

        if lowerstrategy is not None:
            assert (lowerstrategy._broker_id is None) or idlib.equal(lowerstrategy._broker_id, counterparty_id), "counterparty_id: %s, lowerstrategy: %s, lowerstrategy._broker_id: %s" % (humanreadable.hr(counterparty_id), humanreadable.hr(lowerstrategy), humanreadable.hr(lowerstrategy._broker_id),)
            lowerstrategy._broker_id = counterparty_id
            self.use_comm_strategy(counterparty_id, CommStrat.Crypto(counterparty_pub_key, lowerstrategy))
        self._upward_inmsg_handler(counterparty_id, decomptext, self._cid_to_cs.get(counterparty_id))

    def _forget_comm_strategy(self, counterparty_id, commstrat=None):
        """
        @precondition This thread must be the DoQ thread.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This thread must be the DoQ thread."

        curcs = self._cid_to_cs.get(counterparty_id)
        if curcs and ((commstrat is None) or (curcs.same(commstrat))):
            debugprint("CryptoCommsHandler: Forgetting comm strategy.  counterparty_id: %s, curcs: %s\n", args=(counterparty_id, curcs,), v=6, vs="commstrats")
            ls = curcs._lowerstrategy
            if ls:
                if isinstance(ls, CommStrat.TCP):
                    self._tcpch.forget_comm_strategy(counterparty_id, ls)

            curcs._lowerstrategy = None
            del self._cid_to_cs[counterparty_id]

    def forget_comm_strategy(self, counterparty_id, commstrat=None):
        """
        If the higher-level code realizes that a comm strategy is failing, they can call
        `forget_comm_strategy()' to get rid of it.

        TODO: have a sorted list instead of just one CS.  Maybe change this to "demote
        commstrat"?  --Zooko 2001-02-04

        XXX XYZ need to pass which CS to forget, here.  --Zooko 2001-02-05
        """
        if DoQ.doq.is_currently_doq():
            self._forget_comm_strategy(counterparty_id, commstrat)
        else:
            DoQ.doq.add_task(self._forget_comm_strategy, args=(counterparty_id,commstrat))

    def use_comm_strategy(self, counterparty_id, commstrat, orig_cs=None):
        """
        There are several things to do to with this new suggested the comm strat.

        First, make sure that CryptoCommsHandler has a CommStrat.Crypto for this counterparty.

        Second, choose your favourite among available lowerstrategies.

        Third, if you are replacing the current one with the new one then forget the current one.

        Fourth, start using the new one.

        @param commstrat a CommStrat.Crypto which is suggested to use;  The `_lowerstrategy' may
            or may not be adopted depending on whether it is better than the current one.  If
            you want to force adoption of a new strategy, call `forget_comm_strategy()' first.

        @precondition This thread must be the DoQ thread.: DoQ.doq.is_currently_doq()
        @precondition `counterparty_id' must be a binary id.: idlib.is_binary_id(counterparty_id): "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        @precondition `counterparty_id' must match the commstrat public key.: idlib.equals(idlib.make_id(commstrat._pubkey, 'broker'), counterparty_id): "counterparty_id: %s, commstrat: %s" % (humanreadable.hr(counterparty_id), humanreadable.hr(commstrat),)
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This thread must be the DoQ thread."
        assert idlib.is_binary_id(counterparty_id), "precondition: `counterparty_id' must be a binary id." + " -- " + "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        assert idlib.equals(idlib.make_id(commstrat._pubkey, 'broker'), counterparty_id), "precondition: `counterparty_id' must match the commstrat public key." + " -- " + "counterparty_id: %s, commstrat: %s" % (humanreadable.hr(counterparty_id), humanreadable.hr(commstrat),)

        # If we already have a CommStrat.Crypto object then we'll continue to use it (it might
        # have useful hint information in it) instead of the new one, but we'll examine the new
        # one in order to consider taking the newly suggested lowerstrategy.

        curcs = self._cid_to_cs.get(counterparty_id)
        if curcs:
            assert curcs._pubkey == commstrat._pubkey
            # This call to `choose_best_strategy()' choosing between the newly suggested lowerstrat and the one that is current stored in CryptoCommsHandler's _cid_to_cs dict.
            # The winner gets passed down to TCPCh (if it is a TCP comm strat), where `choose_best_strategy()' will be called again, to choose between it and the one that is current in TCPCommsHandler's _cid_to_cs dict.
            preferredlcs = CommStrat.choose_best_strategy(curcs._lowerstrategy, commstrat._lowerstrategy)
            curcs._lowerstrategy = preferredlcs
            # XXX why the dependency on the type?
            # answer: in the future, this will go away, when the CommStrat.TCP itself manages itself and we don't need to inform the _tcpch about it.
            if isinstance(curcs._lowerstrategy, CommStrat.TCP):
                self._tcpch.use_comm_strategy(counterparty_id, curcs._lowerstrategy)
        else:
            # New crypto comm strat!
            self._cid_to_cs[counterparty_id] = commstrat
            self._mesgen.store_key(commstrat._pubkey)
            if isinstance(commstrat._lowerstrategy, CommStrat.TCP):
                self._tcpch.use_comm_strategy(counterparty_id, commstrat._lowerstrategy)

    def get_id(self):
        return idlib.canonicalize(self._mesgen.get_id(), "broker")

    def get_public_key(self):
        return self._mesgen.get_public_key()

    def forget_old_comm_strategies(self):
        """Remove all non-useful CommStrat's from our internal caches"""
        for cid, cs in self._cid_to_cs.items():
            if cs and not cs.is_useful():
                self.forget_comm_strategy(cid, cs)
        # we don't need to call self._tcpch.forget_old_comm_strategies() as our loop above should
        # have removed all TCP CommStrats associated with any Crypto commstrats that were useless.

# Generic stuff
NAME_OF_THIS_MODULE="CryptoCommsHandler"

mojo_test_flag = 1

def run():
    import RunTests
    RunTests.runTests(NAME_OF_THIS_MODULE)

#### this runs if you import this module by itself
if __name__ == '__main__':
    run()

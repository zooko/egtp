#!/usr/bin/env python
#
#  Copyright (c) 2002 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: MojoTransaction.py,v 1.9 2002/03/28 18:39:50 zooko Exp $'


# standard modules
import copy
import exceptions
import math
import os
from sha import sha
import string
import sys
import threading
import time
import traceback
from traceback import print_stack, print_exc
import types
import pickle

# pyutil modules
from config import DEBUG_MODE
from debugprint import debugprint

# Mojo Nation modules
import Cache
from CommHints import HINT_EXPECT_RESPONSE, HINT_EXPECT_MORE_TRANSACTIONS, HINT_EXPECT_NO_MORE_COMMS, HINT_EXPECT_TO_RESPOND, HINT_THIS_IS_A_RESPONSE, HINT_NO_HINT
import CommStrat
import CommsError
import Conversation
import CryptoCommsHandler
import DoQ
import ListenerManager
true = 1
false = 0
from MojoHandicapper import MojoHandicapper
import MojoKey
import MojoMessage
import MojoTransaction
import RelayListener
import TCPCommsHandler
from UnreliableHandicapper import UnreliableHandicapper
import confutils
from confutils import confman
import counterparties
from dictutil import setdefault
from humanreadable import hr
import idlib
import ipaddresslib
import loggedthreading
import mencode
import mesgen
import mojosixbit
import mojoutil
from mojoutil import strpopL, intorlongpopL
import randsource
import std
import timeutil
import whrandom

from interfaces import *


# make users throttle a lot less than the metatracker
if confman.is_true_bool(('YES_NO', 'RUN_META_TRACKER',)):
    MAX_TIME_BETWEEN_IDLE = 90  # 90 seconds
else:
    MAX_TIME_BETWEEN_IDLE = 180  # three minutes

  
class LookupHand(ILookupHandler):
    def __init__(self, counterparty_id, msg, ch, hint=HINT_NO_HINT, fast_fail_handler=None, timeout=300):
        self._counterparty_id = counterparty_id
        self._msg = msg
        self._ch = ch
        self._hint = hint
        self._fast_fail_handler = fast_fail_handler
        self._timeout = timeout

    def result(self, value):
        """
        @precondition `value' must be a dict.: type(value) is types.DictType: "value: %s :: %s" % (hr(value), hr(type(value)),)
        """
        assert type(value) is types.DictType, "precondition: `value' must be a dict." + " -- " + "value: %s :: %s" % (hr(value), hr(type(value)),)

        self._ch.use_comm_strategy(self._counterparty_id, CommStrat.dict_to_strategy(value["connection strategies"][0], mtm=self._ch._tcpch._mtm))
        self._ch.send_msg(self._counterparty_id, self._msg, hint=self._hint, fast_fail_handler=self._fast_fail_handler, timeout=self._timeout)

    def fail(self):
        # Hrm?  Not sure what to do here....  --Zooko 2002-01-27
        debugprint("%s.fail()\n", args=(self,))
        pass

"""
When any message arrives that initiates a new mojotransaction then the appropriate "receive
func" that you registered will be called, but only after the counterparty has been charged the
appropriate amount.  How much is the appropriate amount?  That is determined by a dymanic 2nd
best price auctioning system.
"""

class Widget:
    def __init__(self, counterparty_id, firstmsgId=None):
        """
        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        """
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)

        counterparty_id = idlib.canonicalize(counterparty_id, "broker")

        self._counterparty_id=counterparty_id
        self._firstmsgId=firstmsgId

    def __repr__(self):
        return "<MojoTransaction.Widget instance (id: %x), counterparty_id: %s, conversation_id: %s>" % \
               (id(self), hr(self._counterparty_id), hr(self._firstmsgId))

    def get_counterparty_id(self):
        return self._counterparty_id

    def get_conversation_id(self):
        return idlib.make_id_from_uniq(uniq=self._firstmsgId, thingtype='conversation')
        

class Error(exceptions.StandardError): pass
class FailureError(Error): pass # FailureError is for failures in the conversation/transaction layer
class PricerError(Error): pass

class ResponseMarker: pass

# The following symbols really just belong here in MojoTransaction.py, but Python's inability to do mutually recursive modules means that I can't access ConversationManager from here and also have ConversationManager access these symbols from Conversation.py.  So I'll just shove them into std.  Bleah.  --Zooko 2000-09-28

# possible return value from an incoming message handler. # `ASYNC_RESPONSE' means I'll provide the response later.
ASYNC_RESPONSE = ResponseMarker()

# possible return value from an incoming message handler. # `NO_RESPONSE' means that the correct, permanent, immutable response to the incoming message is to send no response.  Mappings from incoming messages to responses are immutable: you MUST NOT change your mind and send a response later after you have returned `NO_RESPONSE'.  If you mean "I have no response right now, but later I'll come up with the correct, permanent, immutable response.", then return `ASYNC_RESPONSE'.
NO_RESPONSE = ResponseMarker()

# Currently, handlers that handles _responding_ messages are assumed to have no response (that is: every transaction is a two-move protocol), so if you return `None' (the default return value in Python, same as what happens if you have no return statement at all), then it translates to `NO_RESPONSE' for you.  It wouldn't hurt to go ahead and return `NO_RESPONSE' from those handlers, if you wish to emphasize that they are there are no more moves in the protocol.

# XXX this is very bad to be adding member to another module at run time!  please use this module's references to the above instead -g
std.ASYNC_RESPONSE = ASYNC_RESPONSE
std.NO_RESPONSE = NO_RESPONSE

MIN_HELLO_DELAY=45 # never send hellos to MTs more often than this, even if you have new contact info
MIN_REDUNDANT_HELLO_DELAY=450 # never send the same contact info to MTs more often than this

class MojoTransactionManager:
    """
    There are basically two interfaces to MojoTransactionManager, one for
    handling transactions initiated by you and satisfied by a remote broker
    acting as a server, and one for handling transactions initiated by a remote
    broker acting as client and satisfied by you.

    If you want to handle incoming request messages (for example, you are a
    block server and you want to handle incoming 'get block' messages), then you
    define a handler func, which is a function that takes two arguments named
    'widget' and 'msgbody', and returns either a tuple of (response, commhints)
    or else an instance of ResponseMarker.  The response, if any, will be sent
    back to the client.  See the documentation for the ResponseMarkers, above.

    If you want to initiate a transaction with a remote broker acting as server,
    call `MojoTransactionManager.initiate()', passing the id of the remote
    broker, the contents of the query message, and optionally a callback
    function that will be called when the transaction completes or fails.

    For an example of server behavior, see "server/merchant/BlockServerEGTP.py".  For an example
    of client behavior, see "common/Paytool.py".
    """
    def __init__(self, lookupman, discoveryman, pt=None, announced_service_dicts=[], handler_funcs={}, serialized=None, listenport=None, recoverdb=true, pickyport=false, dontbind=false, neverpoll=false, keyID=None, allow_send_metainfo=true, allownonrouteableip=false):
        """
        @param lookupman an object which implements the ILookupManager interface;  MojoTransaction uses the lookupman to get fresh EGTP addresses for counterparty_id's (i.e. to find out the current IP address or current relay server of a given public key ID).
        @param discoveryman an object which implements the IDiscoveryManager interface;  MojoTransaction passes this to RelayListener, which uses the discoveryman to find relay servers.

        @param dontbind `true' if and only if you don't want to bind and listen to a port
        @param neverpoll `true' if you want to override the confman['POLL_RELAYER'] and force it to false;  This is for the Payment MTM -- otherwise you should just use confman.
        @param allownonrouteableip `true' if you want the MTM to ignore the fact that its detected IP address is non-routeable and go ahead and report it as a valid comm strategy;  This is for testing, although it might also be useful some day for routing within a LAN.

        @precondition `announced_service_dicts' must be a list.: type(announced_service_dicts) == types.ListType: "announced_service_dicts: %s" % hr(announced_service_dicts)
        @precondition `handler_funcs' must be a dict.: type(handler_funcs) == types.DictType: "handler_funcs: %s" % hr(handler_funcs)
        @precondition `listenport' must be a non-negative integer or `None'.: (listenport is None) or ((type(listenport) == types.IntType) and (listenport > 0)): "listenport: %s" % hr(listenport)
        @precondition `lookupman' must be an instance of interfaces.ILookupManager.: isinstance(lookupman, ILookupManager): "lookupman: %s :: %s" % (hr(lookupman), hr(type(lookupman)),)
        @precondition `discoveryman' must be an instance of interfaces.IDiscoveryManager.: isinstance(discoveryman, IDiscoveryManager): "discoveryman: %s :: %s" % (hr(discoveryman), hr(type(discoveryman)),)
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq(): "currentThread(): %s" % hr(threading.currentThread())
        """
        assert type(announced_service_dicts) == types.ListType, "precondition: `announced_service_dicts' must be a list." + " -- " + "announced_service_dicts: %s" % hr(announced_service_dicts)
        assert type(handler_funcs) == types.DictType, "precondition: `handler_funcs' must be a dict." + " -- " + "handler_funcs: %s" % hr(handler_funcs)
        assert (listenport is None) or ((type(listenport) == types.IntType) and (listenport > 0)), "precondition: `listenport' must be a non-negative integer or `None'." + " -- " + "listenport: %s" % hr(listenport)
        assert isinstance(lookupman, ILookupManager), "precondition: `lookupman' must be an instance of interfaces.ILookupManager." + " -- " + "lookupman: %s :: %s" % (hr(lookupman), hr(type(lookupman)),)
        assert isinstance(discoveryman, IDiscoveryManager), "precondition: `discoveryman' must be an instance of interfaces.IDiscoveryManager." + " -- " + "discoveryman: %s :: %s" % (hr(discoveryman), hr(type(discoveryman)),)
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ." + " -- " + "currentThread(): %s" % hr(threading.currentThread())

        self._shuttingdownflag = false

        self._lookupman = lookupman
        self._discoveryman = discoveryman

        if handler_funcs:
            for i in handler_funcs.keys():
                assert type(i) is types.StringType
            for i in handler_funcs.values():
                assert callable(i)

        self.__announced_service_dicts=copy.copy(announced_service_dicts)
        self._handicapper=MojoHandicapper()

        self._allow_send_metainfo = allow_send_metainfo  # controls if we allow adding our metainfo to outgoing messages on occasion
        self.__counterparties_metainfo_sent_to_map = Cache.StatsCacheSingleThreaded(maxitems=10000, autoexpireinterval=600, autoexpireparams={'maxage': 1800})
        self.__need_sequence_update = true  # determines if we update our sequence number when generating a hello
        self._lasthellotime=0 # to prevent sending redundant hellos too often
        self._contactinfochangedtime = 0

        self._metatrackers_sent_hello = []  # list of (id, info) tuples of metatrackers we most recently said hello to

        # a map of counterpartyids -> the last time we tried sending a token to them in order to stay paid up
        # (used as a quick 'works in most all cases' hack to prevent sending several tokens to someone at once
        # to stay paid up)
        self._stay_paid_up_time_map = Cache.StatsCacheSingleThreaded(maxitems=5000, autoexpireinterval=300, autoexpireparams={'maxage': 60})

        if handler_funcs:
            self._handler_funcs=copy.copy(handler_funcs)
        else:
            self._handler_funcs={}

        dbparentdir=os.path.expandvars(confman.dict["PATH"]["MOJO_TRANSACTION_MANAGER_DB_DIR"])
        if (serialized is None) and (keyID is None):
            # if not testing, generate new, secret, secure one
            self._mesgen=mesgen.create_MessageMaker(dbparentdir=dbparentdir, recoverdb=recoverdb)
        else:
            if keyID and dbparentdir:
                self._mesgen=mesgen.MessageMaker(dir=os.path.join(dbparentdir, keyID), serialized=serialized, recoverdb=recoverdb)
            else:
                self._mesgen=mesgen.MessageMaker(dbparentdir=dbparentdir, serialized=serialized, recoverdb=recoverdb)

        self._dbdir=os.path.join(dbparentdir, idlib.to_mojosixbit(self._mesgen.get_id()))

        self.response_times = {}
        self._responsetimesold = {}
        self._load_response_times()
        self._cm=Conversation.ConversationManager(self)
        # If `listenport' is None, we can choose any port we like.  We'll choose one determined by the first few bits
        # of our pubkeyid, and make sure it is higher than 1025 and lower than 32767.
        if listenport is None:
            FLOOR=1026
            CEIL=32766
            listenport = ((ord(self._mesgen.get_id()[0]) * 256 + ord(self._mesgen.get_id()[1])) % (CEIL - FLOOR)) + FLOOR

        tcpch = TCPCommsHandler.TCPCommsHandler(mtm=self, listenport=listenport, pickyport=pickyport, dontbind=dontbind)
        self._ch=CryptoCommsHandler.CryptoCommsHandler(mesgen=self._mesgen, tcpch=tcpch)

        self._listenermanager = ListenerManager.ListenerManager(cryptol=self._ch, tcpl=tcpch, relayl=RelayListener.RelayListener(self, discoveryman=self._discoveryman, neverpoll=neverpoll), mtm=self, allownonrouteableip=allownonrouteableip)

        DoQ.doq.add_task(self._periodic_cleanup, delay=150)

        self._keeper=counterparties.CounterpartyObjectKeeper(dbparentdir, local_id=self.get_id(), recoverdb=true)
        # IMPORTANT NOTE:  handicappers are ordered as some of them are in-progress multipliers (such as
        # the performance handicappers which should come after price so that they can scale independently
        # of later handicappers values)
        # When reading the following list, remember that all scalar additives are squared before
        # being added.  The "@returns" doco below is _before_ squaring.  All "@returns" numbers
        # below are additives unless specified to be multipliers.

        # for all msgtypes
        #  @returns 1000 if counterparty is "unreliable";  With default settings, you are unreliable if you have dropped more than 30% of queries or more than 2000 queries throughout all history.
        # DISQUALIFIES counterparties.  The above line is incorrect.
        self.get_handicapper().add_handicapper(UnreliableHandicapper(self._keeper, self.get_id()))

        # for msgtype in ('are there messages',)
        #  @returns 500 if counterparty is not the currently preferred (== most recently advertised) relay server.
        self.get_handicapper().add_handicapper(self._listenermanager._relayl.compute_handicap_prefer_current, mtypes=('are there messages',))

        # significantly handicap counterparties that haven't been responding to their messages recently at all or fast enough
        self.get_handicapper().add_handicapper(self._cm.pending_responses_handicapper)

        # this is used to prevent >1 update from occurring at the same time
        self.__handler_funcs_and_services_dicts_update_lock=threading.Lock()

        self.set_pt(pt)

        self._responsetimesdirty = false # `true' iff the response times stats have been changed and need to be saved to disk;  When you change this flag from `false' to `true', you schedule a save task for 10 minutes later.  When the save task goes off it changes the flag from `true' to `false'.

    def start_listening(self):
        self._listenermanager.start_listening(inmsg_handler_func=self._cm.handle_raw_message)
        self.send_hello_to_meta_trackers()

    def stop_listening(self):
        self._ch.stop_listening()

    def is_listening(self):
        return self._ch.is_listening()

    def _periodic_cleanup(self):
        """put any simple cache cleanup tasks you need to have happen every 2-3 minutes in here"""
        if self._shuttingdownflag:
            return
        try:
            self._ch.forget_old_comm_strategies()
        finally:
            DoQ.doq.add_task(self._periodic_cleanup, delay=150)

    def set_pt(self, pt):
        self._pt = pt
        if self._pt:
            self._pt._register_omtm(self)
    
    def server_thread_join(self, t=1000000000):
        time.sleep(31000000L)

    def get_handicapper(self):
        return self._handicapper

    def clear_all_handler_funcs(self):
        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            self._handler_funcs={}
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()
            pass
    
    def clear_all_announced_services(self):
        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            self._announced_service_dicts = {}
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()
            pass

    def _shutdown_members(self):
        debugprint("%s._shutdown_members()\n", args=(self,))
        for member in ('_blobserver', '_handicapper', '_keeper', '_mesgen', '_metamtm', '_cm', '_reqhandler', '_listenermanager',):
            if hasattr(self, member):
                o = getattr(self, member)
                if hasattr(o, 'shutdown'):
                    o.shutdown()
                delattr(self, member)

    def shutdown(self):
        if self._shuttingdownflag:
            return
        self._shuttingdownflag = true
        debugprint("%s.shutdown() entering\n", args=(self,))
        self.clear_all_announced_services()
        self.clear_all_handler_funcs()
        self._cm.shutdown()
        self._ch.stop_listening()
        self._ch.shutdown()
        self._shutdown_members()
        self._save_response_times()
        debugprint("%s.shutdown() exiting\n", args=(self,))

    def _load_response_times(self):
        try:
            f = open(os.path.join(self._dbdir, "response_times"), 'r')
            s = f.read()
            f.close()
            self.response_times = pickle.loads(s)
        except:
            debugprint("Creating a new global response_times dict.\n", vs="MojoTransaction", v=2)
            self.response_times = {}
        self._responsetimesdirty = false
  
    def _initiate_save_response_times_task_idempotent(self):
        MIN_DELAY = 10 * 60
        # Save it to disk, but not more often than once every 10 minutes.
        if not self._responsetimesdirty:
            DoQ.doq.add_task(self._save_response_times, delay=MIN_DELAY)
            self._responsetimesdirty = true

    def _save_response_times(self):
        debugprint("Saving global response_times dict.\n", vs="MojoTransaction", v=2)
        f = open(os.path.join(self._dbdir, "response_times"), 'w')
        f.write(pickle.dumps(self.response_times))
        f.close()
        self._responsetimesdirty = false
     
    def add_handler_funcs(self, updated_handler_funcs_dict):
        """Add more handler_funcs to this MTM or redefine current ones."""
        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            self._handler_funcs.update(updated_handler_funcs_dict)
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()
        self._hello_sequence_num_needs_increasing()

    def add_announced_services(self, service_dict_list):
        """
        Add more announced services to our list of servers we run.

        @precondition `service_dict_list' must be a list.: type(service_dict_list) == types.ListType: "service_dict_list: %s" % hr(service_dict_list)
        """
        assert type(service_dict_list) == types.ListType, "`service_dict_list' must be a list." + " -- " + "service_dict_list: %s" % hr(service_dict_list)

        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            assert type(self.__announced_service_dicts) == types.ListType, "self.__announced_service_dicts: %s" % hr(self.__announced_service_dicts)
            self.__announced_service_dicts.extend(service_dict_list)
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()
            pass
        self._hello_sequence_num_needs_increasing()
    
    def remove_handler_funcs(self, message_type_list):
        """
        remove handler functions for the specified message types.
        """
        assert type(message_type_list) == types.ListType, "%s is not a list." % hr(message_type_list)
        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            for msgtype in message_type_list:
                if self._handler_funcs.has_key(msgtype):
                    del self._handler_funcs[msgtype]
                    self._hello_sequence_num_needs_increasing()
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()

    def remove_announced_services(self, service_name_list, sendhello=true):
        """
        remove service announcements for the given service types
        """
        assert type(service_name_list) == types.ListType, "%s is not a list." % hr(service_name_list)
        self.__handler_funcs_and_services_dicts_update_lock.acquire()
        try:
            new_service_dicts = []
            for servicedict in self.__announced_service_dicts:
                for servicename in service_name_list:
                    if servicedict.get('type') == servicename:
                        self._hello_sequence_num_needs_increasing()
                        break
                else:
                    new_service_dicts.append(servicedict)
            self.__announced_service_dicts[:] = new_service_dicts
        finally:
            self.__handler_funcs_and_services_dicts_update_lock.release()

    def send_hello_to_meta_trackers(self):
        # debugprint("xxxxxxx %s.send_hello_to_meta_trackers()\n", args=(self,))
        self.__announce_self_to_id_trackers()

    def _hello_sequence_num_needs_increasing(self):
        # debugprint("xxxxxxx %s._hello_sequence_num_needs_increasing()\n", args=(self,))
        if not self.__need_sequence_update:
            self.__need_sequence_update = true

    def _get_our_hello_msgbody(self):
        """
        @returns a contact info dict which can have no comm strategies if there is no strategy yet (which can happen in practice because you haven't found a relayer to announce yet)
        """
        (cs, newflag,) = self._listenermanager.get_comm_strategy_and_newflag()
        # debugprint("xxxxxxx %s._get_our_hello_msgbody(); cs: %s, newflag: %s\n", args=(self, cs, newflag,))

        if newflag:
            self._hello_sequence_num_needs_increasing()
            # debugprint("our current commstrat: %s\n", args=(cs,), v=0, vs="commstrats")

        hello_body={}
        if cs:
            hello_body['connection strategies'] = [cs.to_dict()]

        if len(self.__announced_service_dicts) > 0:
            hello_body['services']=self.__announced_service_dicts
        hello_body['broker version'] = confman.dict.get("BROKER_VERSION_STR", "I'm not telling!")
        hello_body['platform'] = confutils.platform # XXX Jim says: "This is to be removed after the beta period."  --Zooko 2000-08-22

        hello_body['sequence num'] = self.get_hello_sequence_num()
        hello_body['dynamic pricing'] = "true" # This was for smooth changeover and can now be grandfathered out.  --Zooko 2001-09-06

        return hello_body

    def get_hello_sequence_num(self, timer=timeutil.timer):
        """
        Get our current hello sequence number, incrementing it and
        saving it to the config file if it needs updating.
        """
        seqconfkey = "MTM_HELLO_SEQUENCE_NUMS"
        asciiid = idlib.to_ascii(self.get_id())
        needtosave = false
        if not confman.dict.has_key(seqconfkey):
            confman.dict[seqconfkey] = {}
            needtosave = true
        if not confman.dict[seqconfkey].has_key(asciiid):
            confman.dict[seqconfkey][asciiid] = strpopL(1)
            needtosave = true
        if self.__need_sequence_update:
            self.__need_sequence_update = false
            confman.dict[seqconfkey][asciiid] = strpopL(intorlongpopL(confman.dict[seqconfkey][asciiid]) + 1)
            needtosave = true
            # wipe the cache of who we've sent metainfo to since it is now false as our metainfo has been updated
            self.__counterparties_metainfo_sent_to_map.expire(maxage=0)
        if needtosave:
            self._contactinfochangedtime = timer.time()
            # save the current sequence number in the config file so that we never lower it
            # (XXX storing it somewhere other than the cfg file such as the mtmdb/<id>/ directory
            # would be a good idea before we implement persistent metainfo... -greg)
            confman.save()

        return intorlongpopL(confman.dict[seqconfkey][asciiid])

    def get_contact_info(self):
        """
        Return an info dict about ourselves suitable for use with
        MetaTrackerLib (basically this is what a meta tracker lookup
        of us would return)

        @returns a contact info dict with no comm strategies if there is no strategy yet (which can happen in practice because you haven't found a relayer to announce yet)
        """
        hello_dict=self._get_our_hello_msgbody()
        metainfo_dict = copy.copy(hello_dict)
        return metainfo_dict

    def __announce_self_to_id_trackers(self, timer=timeutil.timer):
        if self._shuttingdownflag:
            return

        now = timer.time()
        timesincelasthello = now - self._lasthellotime

        if timesincelasthello < MIN_HELLO_DELAY:
            # never send hellos to MTs more often than this, even if you have new contact info
            # but if you have new information then schedule a retry after this amount of delay.
            if self._lasthellotime < self._contactinfochangedtime:
                DoQ.doq.add_task(self.__announce_self_to_id_trackers, delay=(MIN_HELLO_DELAY - timesincelasthello) + 1)
            return

        if (self._lasthellotime > self._contactinfochangedtime) and (timesincelasthello < MIN_REDUNDANT_HELLO_DELAY):
            return # never send the same contact info to MTs more often than this

        self._lasthellotime = now

        hello_body = self._get_our_hello_msgbody()

        if not hello_body.has_key('connection strategies'):
            # Hm.  We haven't figured out how people can talk to us yet.  Might as well not bother announcing then.
            return

        assert ((type(hello_body) is types.DictType) and (hello_body.has_key("connection strategies")) and (hello_body.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(hello_body) is types.InstanceType) and (isinstance(hello_body, CommStrat)) and (hello_body._broker_id is not None)), "hello_body: %s" % hr(hello_body)
        assert idlib.equal(self.get_id(), CommStrat.addr_to_id(hello_body)), "self.get_id(): %s, hello_body: %s" % (hr(self.get_id()), hr(hello_body),)
        self._lookupman.publish(self.get_id(), hello_body)

    def send_goodbye_to_metatrackers(self):
        """Send sign off message to meta/id trackers we most recently said hello to; this does not wait for the send to succeed!"""
        for (metatracker_id, metatracker_info) in self._metatrackers_sent_hello:
            if self.get_id() == metatracker_id:
                continue
            self.initiate(counterparty_id=metatracker_id, conversationtype='goodbye', firstmsgbody={}, timeout=1)

    def get_public_key(self):
        return self._mesgen.get_public_key()

    def get_id(self):
        return self._ch.get_id()

    def get_comm_strategy(self):
        """
        @returns the comm strategy in the form of an instance of CommStrat.CommStrat, or `None' if there is no strategy yet (which can happen in practice because you haven't found a relayer to announce yet)
        """
        return self._listenermanager.get_comm_strategy_and_newflag()[0]

    def serialize(self):
        return mencode.mencode({'session keeper': self._mesgen._session_keeper.serialize()})

    def respond_with(self, prevmsgId, msgbody, mojoheader=None, hint=HINT_NO_HINT):
        """
        You must ensure that you call `respond_with()' using a given `prevmsgId', no more than
        one time in the history of the universe.  Also you must not call `response_with()' using
        a given `prevmsgId' if you returned a "response body" return value from the handler
        which originally processed the previous message.  In practice, this is pretty easy to
        ensure by relying upon MojoTransaction's guarantee that your handler will be invoked
        exactly one time in the history of the universe for one message.

        @param prevmsgId the id of the message to which this is a response
        @param msgbody the body of the response
        @param mojoheader is an optional 'mojo header' to send with this response.  It should not be used
            by normal callers as it is parsed and interpreted by MojoTransaction internally on the receiving end.

        @precondition `msgbody' is just the innermost message body, not having a "mojo header" or "mojo message" subdict.: (type(msgbody) != types.DictType) or ((not msgbody.has_key('mojo header')) and (not msgbody.has_key('mojo message'))): "msgbody: %s" % hr(msgbody)

        @precondition internal1: self._cm._map_inmsgid_to_info.get(prevmsgId) is not None: "prevmsgId: %s, msgbody: %s" % (hr(prevmsgId), hr(msgbody))
        @precondition internal2: (type(self._cm._map_inmsgid_to_info.get(prevmsgId)) == types.TupleType) or (type(self._cm._map_inmsgid_to_info.get(prevmsgId)) == types.ListType): "self._cm._map_inmsgid_to_info.get(prevmsgId): %s :: %s" % (hr(self._cm._map_inmsgid_to_info.get(prevmsgId)), hr(type(self._cm._map_inmsgid_to_info.get(prevmsgId))))
        @precondition internal3: self._cm._map_inmsgid_to_info.get(prevmsgId)[2] == Conversation.EXPECTING_RESPONSE: "self._cm._map_inmsgid_to_info.get(prevmsgId): %s" % hr(self._cm._map_inmsgid_to_info.get(prevmsgId))
        @precondition internal4: idlib.is_sloppy_id(self._cm._map_inmsgid_to_info.get(prevmsgId)[0]): "self._cm._map_inmsgid_to_info.get(prevmsgId)[0]: %s :: %s" % (hr(self._cm._map_inmsgid_to_info.get(prevmsgId)[0]), hr(type(self._cm._map_inmsgid_to_info.get(prevmsgId)[0])))
        """
        assert (type(msgbody) != types.DictType) or ((not msgbody.has_key('mojo header')) and (not msgbody.has_key('mojo message'))), "precondition: `msgbody' is just the innermost message body, not having a \"mojo header\" or \"mojo message\" subdict." + " -- " + "msgbody: %s" % hr(msgbody)
        assert self._cm._map_inmsgid_to_info.get(prevmsgId) is not None, "precondition: internal1" + " -- " + "prevmsgId: %s, msgbody: %s" % (hr(prevmsgId), hr(msgbody))
        assert (type(self._cm._map_inmsgid_to_info.get(prevmsgId)) == types.TupleType) or (type(self._cm._map_inmsgid_to_info.get(prevmsgId)) == types.ListType), "precondition: internal2" + " -- " + "self._cm._map_inmsgid_to_info.get(prevmsgId): %s :: %s" % (hr(self._cm._map_inmsgid_to_info.get(prevmsgId)), hr(type(self._cm._map_inmsgid_to_info.get(prevmsgId))))
        assert self._cm._map_inmsgid_to_info.get(prevmsgId)[2] == Conversation.EXPECTING_RESPONSE, "precondition: internal3" + " -- " + "self._cm._map_inmsgid_to_info.get(prevmsgId): %s" % hr(self._cm._map_inmsgid_to_info.get(prevmsgId))
        assert idlib.is_sloppy_id(self._cm._map_inmsgid_to_info.get(prevmsgId)[0]), "precondition: internal4" + " -- " + "self._cm._map_inmsgid_to_info.get(prevmsgId)[0]: %s :: %s" % (hr(self._cm._map_inmsgid_to_info.get(prevmsgId)[0]), hr(type(self._cm._map_inmsgid_to_info.get(prevmsgId)[0])))

        counterparty_id = self._cm._map_inmsgid_to_info.get(prevmsgId, [''])[0]  # XXX HACK (ideally this would be in Conversation or Conversation and MojoTransaction would be merged)

        # include our metainfo in messages the first time we send a message to a counterparty
        # (or again when it has been updated; this map is emptied when our metainfo changes)
        mymetainfo = None
        if self._allow_send_metainfo and not self.__counterparties_metainfo_sent_to_map.has_key(counterparty_id):
            mymetainfo = self._get_our_hello_msgbody()
            self.__counterparties_metainfo_sent_to_map[counterparty_id] = None

        body = {}
        if msgbody is not None:
            body['mojo message'] = msgbody
        if mojoheader:
            body['mojo header'] = mojoheader

        self._cm.send_response(prevmsgId, body, mymetainfo=mymetainfo, hint=hint)

    def handle_initiating_message(self, counterparty_id, msgtype, msgbody, firstmsgId):
        """
        Invoke the appropriate server func.

        @returns the full msg body to be sent back in response (containing a 'mojo header' and/or 'mojo message' subdict) in dict form, or None, or std.ASYNC_RESPONSE

        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)

        @postcondition Result must be either None or std.ASYNC_REPONSE or else the full msg body dict, containing either a "mojo header" subdict or a "mojo message" subdict or both.: (not result) or (result is std.ASYNC_RESPONSE) or result.has_key('mojo header') or result.has_key('mojo message'): "result: %s" % hr(result)
        """ 
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)

        serverfunc = self._handler_funcs.get(msgtype)
        if not serverfunc:
            if confman.get('MAX_VERBOSITY', 0) >= 3:
                debugprint("DEBUG: received a message of unhandled type `%s': `%s'.\n", args=(msgtype, msgbody), v=3, vs="debug")
            else:
                debugprint("DEBUG: received a message of unhandled type `%s'.\n", args=(msgtype,), v=1, vs="debug")

            # force the next message sent to counterparty_id to include our current metainfo
            if self.__counterparties_metainfo_sent_to_map.has_key(counterparty_id):
                try:
                    del self.__counterparties_metainfo_sent_to_map[counterparty_id]
                except KeyError:
                    pass
            # TODO send an advisory message to counterparty_id containing our metainfo if we haven't sent one recently (prevent DoS)
            return None

        widget=Widget(counterparty_id, firstmsgId=firstmsgId)

        mojomessagedict=msgbody['mojo message']

        widget = Widget(counterparty_id, firstmsgId)
        # Okay, now invoke the server func:
        result = serverfunc(widget, msgbody['mojo message'])

        if result is MojoTransaction.NO_RESPONSE:
            self._cm.drop_request_state(firstmsgId)
            return NO_RESPONSE

        if result is MojoTransaction.ASYNC_RESPONSE:
            return MojoTransaction.ASYNC_RESPONSE

        if (type(result) in (types.TupleType, types.ListType,)) and (len(result) == 2) and Conversation.is_mojo_message(result[0]) and CommHints.is_hint(result[1]):
            result = result[0]
            hint = result[1]
        else:
            hint = HINT_NO_HINT

        self.respond_with(firstmsgId, result, hint=hint)
        return None

    def initiate(self, counterparty_id, conversationtype, firstmsgbody, outcome_func=None, timeout=300, notes = None, post_timeout_outcome_func=None, use_dynamic_timeout="iff there is a post_timeout_outcome_func", commstratseqno=None, hint=HINT_NO_HINT):
        """
        Initiates a transaction with the specified counterparty.

        @param counterparty_id the id of the counterparty with whom to transact
        @param conversationtype human readable string "message type" or "conversation type";
            See OurMessages*.py for examples.
        @param firstmsgbody the contents of the initiating message of the transaction;  This
            can be any of the Pythonic types supported by the mencode module, currently
            (in v0.913): integers (ints or longs), strings, None, sequences (lists or tuples)
            and dicts, where the items in the sequences and the keys and values in the dicts
            may be any of these same types.
        @param outcome_func a callback that will be called exactly once with "widget",
            "outcome", "failure_reason", and "notes" keyword arguments;  <p>This func will be
            called with a `failure_reason' argument other than `None' if and only if there is a
            failure below the level of the transaction layer.  Typical causes of failure below
            this layer include communications error, timeout, or failure to pay Mojo.  (Note
            that sometimes your broker _chose_ incur a failure to pay Mojo, for example if the
            counterparty was charging more than you were willing to spend.)  <p>This func will
            be called with an `outcome' if and only if a satisfactory response message is
            received from the counterparty.  The `outcome' can be any of the Pythonic types
            handled by mencode (see above in doc of `firstmsgbody'), and typically is a dict
            with strings as names. <p>The "notes" argument is the same as was passed to
            this initiate call.  This allows data to be passed from initiation code to response
            handling code.
        @param timeout the maximum amount of time before `outcome_func' is called with a
            `failure_reason' indicating timeout if no response message has been received
        @param post_timeout_outcome_func is a callback with the same interface as outcome_func.
            It will only be called if outcome_func has already been called with a failure_reason
            of 'timeout' and the response messages arrives (known as a "post timeout response").  It
            is not guaranteed to be called at all.  The idea of this function is that response
            messages still contain valid data that your application could use even if they took longer
            than expected.
        @param use_dynamic_timeout a flag to indiciate whether a dynamic timeout
            based on previous timings with this kind of message to this counterparty
            would be a good idea.  If no data is available, fall back to using timeout.
            Set this to "never" to indicate never using a dynamic timeout, "always" to indicate
            always, and "iff there is a post_timeout_outcome_func" to indicate 'use one iff
            post_timeout_outcome_func is not None'
        @param commstratseqno the sequence number of the comm strategy which has
            already been tried (i.e., if you are doing a pass-this-along on behalf of an original
            sender, then this should be the commstratseqno that that sender used, which
            told him to forward through you.;  If you attempt a recursive delivery
            mechanism, then you can avoid loops by ensuring that the next contact
            strategy you try has seqno > than this one.  `None' means to always send the
            message to the next hop, regardless, which is what you want when it is a
            message that actually originates with you.
        @param an optional comms hint (see CommHints.py)

        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        @precondition This MTM must not be shutting down.: not self._shuttingdownflag
        """
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)
        assert not self._shuttingdownflag, "precondition: This MTM must not be shutting down."

        counterparty_id = idlib.to_binary(counterparty_id)
        if notes is not None and outcome_func:
            def wrapped_outcome_func(widget, outcome, failure_reason, 
                    outcome_func = outcome_func, notes = notes):
                outcome_func(widget, outcome, failure_reason, notes = notes)
            outcome_func = wrapped_outcome_func
        DoQ.doq.add_task(self._initiate, args=(counterparty_id, conversationtype, firstmsgbody, outcome_func,), kwargs={'timeout': timeout, 'post_timeout_outcome_func': post_timeout_outcome_func, 'use_dynamic_timeout':use_dynamic_timeout, 'commstratseqno': commstratseqno, 'hint': hint})

    def _initiate(self, counterparty_id, conversationtype, firstmsgbody, outcome_func, timeout=300, post_timeout_outcome_func=None, use_dynamic_timeout=None, commstratseqno=None, hint=HINT_NO_HINT):
        """
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."

        counterparty_id = idlib.canonicalize(counterparty_id, "broker")
            
        if confman.is_true_bool(['COUNTERPARTY', 'USE_DYNAMIC_TIMING'], default="yes"):
            if (use_dynamic_timeout == "always" or (use_dynamic_timeout == "iff there is a post_timeout_outcome_func" and post_timeout_outcome_func is not None)):
                counterparty = self._keeper.get_counterparty_object(counterparty_id)
                stat = 'roundtrip_time['+conversationtype+']'
                if counterparty.get_custom_stat(stat) is None:
                    (mu, sigma, ignore) = self.response_times.get(conversationtype, (120, 20, false,))
                    timeout = mu + 2*sigma
                    debugprint("using global average dynamic timeout %s with for %s to %s\n", args=("%0.2f" % timeout, stat, counterparty_id), v=3, vs='counterparty')
                else:
                    (mu, sigma, ignore) = counterparty.get_custom_stat(stat)
                    timeout = mu + 2*sigma
                    debugprint("using dynamic timeout %s with for %s to %s\n", args=("%0.2f" % timeout, stat, counterparty_id), v=3, vs='counterparty')

        timeout = min(mojoutil.intorlongpopL(confman.get('MAX_TIMEOUT', 3600)), timeout)

        def collect_timings(counterparty_id=counterparty_id, start_time=time.time(), conversationtype=conversationtype, self=self):
            """
            Update timing statistics then call outcome_func

            The elapsed time is used to update estimates of mean and
            standard deviation of arrival times.  As a statistical
            tool, a warning is output every time the estimate is under
            by two standard deviations.  The intention is that one
            could use mu + 2*sigma as a timeout.

            The exponential averaging uses a time constant of 10, so
            it takes about 10 packets to learn aout the timeouts.
            This may be too high; it should be a configuration option.
            """
            elapsed_time = time.time() - start_time
            time_constant = float(confman["COUNTERPARTY"]["AVERAGING_TIMESCALE_v2"])
            default_sigma = elapsed_time

            stat = 'roundtrip_time['+conversationtype+']'
            
            counterparty = self._keeper.get_counterparty_object(idlib.canonicalize(counterparty_id, "broker"))
            if counterparty.get_custom_stat(stat) is not None:
                # We already have an estimate of how long it should have taken.
                # How good was our guess?
                try:
                    # defaults get returned only if it's you
                    (mu, sigma, ignore) = counterparty.get_custom_stat(stat, (0, 0, 0))
                    debugprint("dynamic timing: message %s to %s took %s seconds (mu: %s, sigma: %s)\n", args=(stat, counterparty_id, "%0.2f" % elapsed_time, "%0.2f" % mu, "%0.2f" % sigma), v=3, vs="MojoTransaction")
                    if elapsed_time > (mu+2*sigma):
                        # Assuming a normal distribution, 99.7% caught
                        debugprint("dynamic timing: UNUSUALLY LONG DELAY (normal distribution) on message %s to %s (took: %s mu: %s, sigma: %s)\n", args=(stat, counterparty_id, "%0.2f" % elapsed_time, "%0.2f" % mu, "%0.2f" % sigma), v=4, vs="MojoTransaction")
                    if elapsed_time > 6*mu:
                        # Assuming an exponential distribution, 99.7% caught
                        debugprint("dynamic timing: UNUSUALLY LONG DELAY (exponential distribution) on message %s to %s (took: %s mu: %s)\n", args=(stat, counterparty_id, "%0.2f" % elapsed_time, "%0.2f" % mu), v=4, vs="MojoTransaction")
                except TypeError:
                    # Statistics are damaged.  Ignore.
                    debugprint("dynamic timing: deleting damaged statistic %s for %s\n", args=(stat, counterparty_id), v=2, vs="MojoTransaction")
                    # this shouldn't happen, but we should nuke the damaged stat in the event that it does
                    counterparty.delete_custom_stat(stat)

            counterparty.update_custom_stat_weighted_sample_with_deviation(stat, elapsed_time, math.exp(-1./time_constant), default_sigma)

            oldval = self._responsetimesold.get(conversationtype)
            newval = mojoutil.update_weighted_sample(setdefault(self.response_times, conversationtype, None), elapsed_time, math.exp(-1./time_constant), default_sigma)
            self.response_times[conversationtype] = newval
            if (oldval is None) or (abs(oldval[0] - newval[0]) > 0.5) or (abs(oldval[1] - newval[1]) > 0.5):
                self._initiate_save_response_times_task_idempotent()
                self._responsetimesold.update(self.response_times)

        def wrapped_outcome_func_collect_timings(widget=None, outcome=None, failure_reason=None, notes=None, outcome_func=outcome_func, collect_timings=collect_timings):
            if failure_reason != 'timeout':
                collect_timings()
            return outcome_func(widget, outcome, failure_reason)

        def wrapped_post_timeout_outcome_func_collect_timings(outcome=None, failure_reason=None, notes=None, post_timeout_outcome_func=post_timeout_outcome_func, collect_timings=collect_timings):
            debugprint("dynamic timing: late return from %s\n", args=(notes['counterparty_id'],), v=3, vs='MojoTransaction')
            collect_timings()
            widget = Widget(notes['counterparty_id'], notes['first_message_id'])
            if post_timeout_outcome_func is not None:
                return post_timeout_outcome_func(widget=widget, outcome=outcome['mojo message'], failure_reason=failure_reason)
            else:
                return None

        if confman.is_true_bool(['COUNTERPARTY', 'COLLECT_DYNAMIC_TIMING']) and outcome_func:
            outcome_func = wrapped_outcome_func_collect_timings
            post_timeout_outcome_func = wrapped_post_timeout_outcome_func_collect_timings
        ### END DYNAMIC TIMERS code

        mojoheaderdict={}

        bodydict={
            'mojo header': mojoheaderdict,
            'mojo message': firstmsgbody,
            }

        notes = {'outer_outcome_func': outcome_func, 
            'conversationtype': conversationtype, 'firstmsgbody': firstmsgbody, 
            'timeout': timeout,
            'counterparty_id': counterparty_id,
            }
            
        # include our metainfo in messages the first time we send a message to a counterparty
        # (or again when it has been updated; this map is emptied when our metainfo changes)
        mymetainfo = None
        if self._allow_send_metainfo and not self.__counterparties_metainfo_sent_to_map.has_key(counterparty_id):
            mymetainfo = self._get_our_hello_msgbody()
            if not mymetainfo.has_key('connection strategies'):
                # Hm.  We haven't finished choosing a relay server I guess.
                mymetainfo = None
            self.__counterparties_metainfo_sent_to_map[counterparty_id] = None

        first_message_id, msg = self._cm.initiate_and_return_first_message(counterparty_id, conversationtype, bodydict, outcome_func=self._outcome_func_to_do_mojo_header, timeout=timeout, notes=notes, mymetainfo=mymetainfo, post_timeout_outcome_func=post_timeout_outcome_func)

        notes['first_message_id'] = first_message_id

        self.send_message_with_lookup(counterparty_id, msg, timeout=timeout, hint=hint | HINT_EXPECT_RESPONSE, commstratseqno=commstratseqno)

    def _outcome_func_to_do_mojo_header(self, outcome = None, failure_reason = None, notes = None):
        """
        XXX adding yet another feature to this handler (it already has several separate feature not adequately described by "to do mojo header").  The new one is forget a comm strategy if a conversation fails.  --Zooko 2001-05-04
        XXX In the future, we need to keep track of which actual specific comm strategy the conversation was trying to use, and only forget that one, rather than forgetting whatever one we are using *now*.  --Zooko 2001-05-04

        @precondition `outcome' is none or else the full message body, having a "mojo header" or "mojo message" subdict.: (not outcome) or outcome.has_key('mojo header') or outcome.has_key('mojo message'): "outcome: %s" % hr(outcome)
        """
        assert (not outcome) or outcome.has_key('mojo header') or outcome.has_key('mojo message'), "`outcome' is none or else the full message body, having a \"mojo header\" or \"mojo message\" subdict." + " -- " + "outcome: %s" % hr(outcome)

        counterparty_id = notes['counterparty_id']
        outer_outcome_func = notes['outer_outcome_func']
        conversationtype = notes['conversationtype']
        firstmsgbody = notes['firstmsgbody']
        timeout = notes['timeout']

        widget=Widget(counterparty_id)
        widget._firstmsgId = notes['first_message_id']

        counterparty_obj = self._keeper.get_counterparty_object(counterparty_id)

        if failure_reason is not None:
            debugprint("MTM: msgId: %s :: %s with %s, failed, failure_reason: %s\n", args=(widget._firstmsgId, conversationtype, widget.get_counterparty_id(), failure_reason), v=2, vs="Conversation")
            self.forget_comm_strategy(counterparty_id, widget._firstmsgId, outcome=outcome, failure_reason=failure_reason)

            counterparty_obj.decrement_reliability()
            if outer_outcome_func:
                return apply(outer_outcome_func, (), {'widget': widget, 'outcome': outcome, 'failure_reason': failure_reason})
            else:
                return None
        else:
            counterparty_obj.increment_reliability()

        debugprint("MTM: msgId: %s :: %s with %s, completed\n", args=(widget._firstmsgId, conversationtype, widget.get_counterparty_id(),), v=2, vs="Conversation")

        if outcome is not None:
            mojoheader=outcome.get('mojo header', {})
            mojomessage=outcome.get('mojo message')

            if mojoheader.get('result') != "failure":
                # This is a successful happy response message

                # call the callback with the response message
                if outer_outcome_func:
                    return apply(outer_outcome_func, (), {'widget': widget, 'outcome': mojomessage, 'failure_reason': None})
                else:
                    return None
            else:
                # this is some other undefined failure response.
                if outer_outcome_func:
                    return apply(outer_outcome_func, (), {'widget': widget, 'outcome': outcome, 'failure_reason': mojoheader.get('failure_reason', "failure reported in mojoheader")})
                else:
                    return None

    def send_message_with_lookup(self, counterparty_id, msg, timeout=300, hint=HINT_NO_HINT, commstratseqno=None):
        """
        This just calls `send_message_with_lookup_internal()' from the DoQ thread.
       
        But if this _is_ the DoQ thread, then it calls `send_message_with_lookup_internal()' directly.
        """
        if DoQ.doq.is_currently_doq():
            self.send_message_with_lookup_internal(counterparty_id, msg, timeout=timeout, hint=hint)
        else:
            DoQ.doq.add_task(self.send_message_with_lookup_internal, args=(counterparty_id, msg,), kwargs={'timeout': timeout, 'hint': hint, 'commstratseqno': commstratseqno})

    def _ffh(self, msgId, failure_reason=None, bad_commstrat=None, counterparty_id=None):
        """
        An internal use only fast fail handler that calls the conversation properly.

        @param counterparty_id is the id of the counterparty we were sending this message to.
        @param bad_commstrat (if not None) must be the particular comm strategy that the lower layers think is bad.
        """
        # XXX If we were clever we would be able to tell which specific comm strat we used to
        # send the failed message, and we would neg that particular comm strat but not any
        # others that we might know.  But we're not that smart so we'll just brute force it and
        # destroy all contact info for this counterparty and start fresh.
        # On a similar note, greg wrote most of the necessary code here to identify the
        # difference between failure due to bad comm strat (i.e. TCP connection refused) and
        # failure due to some other unknown reason (i.e. timeout), but we can't really discern
        # the difference -- for example if Alice's relay server, Roger, has gone down, then we
        # will think that our message to Alice failed for "some other reason", instead of for
        # having a bad comm strat, but it really does have a bad commstrat.
        # So for now let's brute-force that issue too -- any failure leads to total deletion of
        # all contact info and comm strats.
        if not idlib.is_sloppy_id(counterparty_id):
            debugprint("WARNING: I want a counterparty_id here.  counterparty_id: %s :: %s, msgId: %s, failure_reason: %s, stack trace: %s\n", args=(counterparty_id, type(counterparty_id), msgId, failure_reason, traceback.extract_stack(),), v=1, vs="debug")
        else:
            # failure? count that against their reliability
            counterparty_obj = self._keeper.get_counterparty_object(counterparty_id).decrement_reliability()
            # MetaTrackerLib.neg_contact_info(counterparty_id) # commenting this out in an attempt to separate MetaTrackerLib from MojoTransaction, during the "nEGTP-1" era.  (that is: MetaTrackerLib will hopefully be managed solely by MetaTrackerLookupMan from now on.  This suggests that MTL should not do any caching at all, so that we don't have to neg-cache it.  The Crypto and TCP Comms Handlers are both doing some limited caching already.)  --Zooko 2002-01-28
            self.forget_comm_strategy(counterparty_id, firstmsgId=msgId, failure_reason=failure_reason)

        if bad_commstrat is not None and counterparty_id is not None:
            debugprint("bad comm strategy for %s: %s = %s?\n", args=(counterparty_id, bad_commstrat, bad_commstrat.__dict__.get('_orig_top_cs')), v=3, vs="FastFail")

        debugprint("MojoTransactionManager: Attempt to send %s failed.  Aborting transaction.  failure_reason: %s\n", args=(msgId, failure_reason,), v=5, vs="Conversation")
        if DoQ.doq.is_currently_doq():
            self._cm.fail_conversation(msgId, failure_reason=failure_reason)
        else:
            DoQ.doq.add_task(self._cm.fail_conversation, args=(msgId,), kwargs={'failure_reason': failure_reason})

    def forget_comm_strategy(self, counterparty_id, firstmsgId=None, outcome=None, failure_reason=None):
        # XXX would like to make this have same arguments as normal callbacks.  --Zooko 2001-05-14
        debugprint("MojoTransaction: Forgetting comm strategy.  firstmsgId: %s, failure_reason: %s, counterparty_id: %s\n", args=(firstmsgId, failure_reason, counterparty_id,), v=6, vs="commstrats")
        # MetaTrackerLib.neg_contact_info(counterparty_id) # XXX I think maybe this causes you to starve yourself of known counterparties and suffer a very poor Mojo Net.  --Zooko 2001-05-15
        self._ch.forget_comm_strategy(counterparty_id)

    def send_message_with_lookup_internal(self, counterparty_id, msg, timeout=300, hint=HINT_NO_HINT, commstratseqno=None):
        """
        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        @precondition `msg' must be a string, and non-empty.: (type(msg) is types.StringType) and (len(msg) > 0): "msg: %s" % hr(msg)
        """
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)
        assert (type(msg) is types.StringType) and (len(msg) > 0), "`msg' must be a string, and non-empty." + " -- " + "msg: %s" % hr(msg)

        counterparty_id = idlib.canonicalize(counterparty_id, "broker")

        msgId = idlib.string_to_id(msg)
        def _debugprint(self=self, counterparty_id=counterparty_id, diagstr="", args=(), v=0, vs="conversation"):
            printstr="---> %s: " + diagstr + "\n"
            theseargs=[counterparty_id]

            theseargs.extend(list(args))
            debugprint(printstr, args=theseargs, v=v, vs=vs)

        def outer_fast_fail_handler(msgId=msgId, failure_reason="cannot send message", bad_commstrat=None, counterparty_id=counterparty_id, self=self):
            self._ffh(msgId, failure_reason=failure_reason, bad_commstrat=bad_commstrat, counterparty_id=counterparty_id)

        maxverb = int(confman.dict.get("MAX_VERBOSITY", 0))
        if maxverb >= 5:
            _debugprint(diagstr="sending: %s, %s bytes uncomp", args=(msg, len(msg)), v=5) # super verbose
        elif maxverb >= 4:
            # XXX note, this slows sending down A LOT! calling MojoMessage.getType() calls mdecode() & template check on the message.  The mdecode part is -extremely- slow (esp on big messages).  -greg 11-oct-2000
            # if we want to display this quickly, we'll need to pass the type in from before we called mencode()
            _debugprint(diagstr="sending: (id: %s, type: %s, %s bytes uncomp, ...)", args=(msgId, MojoMessage.getType(msg), len(msg)), v=4) # semi-verbose
        elif maxverb >= 3:
            _debugprint(diagstr="sending: (id %s, %s bytes uncomp, ...)", args=(msgId, len(msg)), v=3)

        def fast_fail_handler(msgId=msgId, failure_reason="cannot send message", bad_commstrat=None, counterparty_id=counterparty_id, _debugprint=_debugprint, self=self, msg=msg, timeout=timeout, outer_fast_fail_handler=outer_fast_fail_handler):
            _debugprint(diagstr="failed to send, forgetting comm strat and trying to look up new one...", v=5)
            # XXX someday, pass `bad_commstrat' to `forget_comm_strategy()' so that we can forget only the bad one.
            # XXX if we kept a list of comm strategies instead of just one, then we could manage remembering comm strats in just one place.
            # Currently we basically have a list of 2 comm strats, one kept in comms handlers and one kept in MetaTrackerLib.
            # Anyway, here we forget the comms handler cs, but preserve the MTL contact info.  --Zooko 2001-05-15
            # self.forget_comm_strategy(counterparty_id, msgId, failure_reason=failure_reason)
            self.forget_comm_strategy(counterparty_id, firstmsgId=msgId, failure_reason=failure_reason)
            self.__query_for_counterparty_and_send(counterparty_id, msg, timeout=timeout, fast_fail_handler=outer_fast_fail_handler)

        # _debugprint(diagstr="sending directly [b] ...", v=15, vs="conversation")
        try:
            self._ch.send_msg(counterparty_id, msg, hint=hint, fast_fail_handler=fast_fail_handler, timeout=timeout, commstratseqno=commstratseqno)
            # _debugprint(diagstr="sent.", v=15, vs="conversation")
        except MemoryError, le:
            if DEBUG_MODE:
                debugprint("MojoTransaction.send_message_with_lookup(): called `_ch.send_msg(%s, msgId:%s)' and got MemoryError: %s\n", args=(counterparty_id, msgId, le), v=0, vs="debug")
            fast_fail_handler(failure_reason=le)
            return
        except CommsError.CannotSendError, le:
            # debugprint("MojoTransaction.send_message_with_lookup(): called `_ch.send_msg(%s, msgId:%s)' and got CannotSendError: %s\n", args=(counterparty_id, msgId, le), v=10, vs="commstrats")
            fast_fail_handler(failure_reason=hr(le))
        # _debugprint(diagstr="sent", v=15)

    def __query_for_counterparty_and_send(self, counterparty_id, msg, timeout=300, fast_fail_handler=None, hint=HINT_NO_HINT):
        def _debugprint(self=self, counterparty_id=counterparty_id, msg=msg, diagstr="", args=(), v=0, vs="conversation"):
            printstr="---> %s: " + diagstr + "\n"
            theseargs=[counterparty_id]

            theseargs.extend(list(args))
            debugprint(printstr, args=theseargs, v=v, vs=vs)

        # _debugprint(diagstr="looking up contact info...", v=15, vs="metatracking")
        lookuphand = LookupHand(counterparty_id, msg, self._ch, hint=hint, fast_fail_handler=fast_fail_handler, timeout=timeout)
        self._lookupman.lookup(counterparty_id, lookuphand)
        # _debugprint(diagstr="done calling nonblocking_get_contact_info...", v=15, vs="metatracking")


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import os
import traceback
import types

# pyutil modules
from debugprint import debugprint

# (old-)EGTP modules
import CommHints
from CommHints import HINT_EXPECT_MORE_TRANSACTIONS
import CommStrat
import DataTypes
import DoQ
import LazySaver
import MojoMessage
import OurMessages
from confutils import confman
import dictutil
from humanreadable import hr
import idlib
import randsource
import timeutil

from interfaces import *

true = 1
false = None

# Number of relayers that you actively poll (because you have, in the past, announced them as being your favorite).  You poll the i'th one every 60 seconds * 2^i, so ones further down the list rarely get polled, but the list also serves as a data structure for voting for the new favorite based on the fact that you've received messages from him, so it should stay around length 8.  --Zooko 2001-09-06
NUM_PREFERRED_RELAYERS = 8

# How often do we call `list_relay_servers()' in order to find new ones?
RELAYER_SHOPPING_DELAY=300

# We never poll any given relayer more frequently than one poll per MIN_POLL_DELAY many seconds.
MIN_POLL_DELAY=60

# How much to handicap any relayer that isn't our current favorite.
STICK_WITH_CURRENT_RELAYER_TUNING_FACTOR=float(500)

class ShoppingResultsHand(IDiscoveryHandler):
    def __init__(self, rl):
        self._rl = rl
        self._outstanding = true
        self._rl._outstandingshoppingtrips = self._rl._outstandingshoppingtrips + 1

    def result(self, value):
        try:
            self._rl._handle_result_of_shopping(value)
        finally:
            if self._outstanding:
                self._rl._outstandingshoppingtrips = self._rl._outstandingshoppingtrips - 1
                self._rl._schedule_shopping_trip_if_needed()
                self._outstanding = false

    def fail(self):
        if self._outstanding:
            self._rl._outstandingshoppingtrips = self._rl._outstandingshoppingtrips - 1
            self._rl._schedule_shopping_trip_if_needed()
            self._outstanding = false

    def soft_timeout(self):
        if self._outstanding:
            self._rl._outstandingshoppingtrips = self._rl._outstandingshoppingtrips - 1
            self._rl._schedule_shopping_trip_if_needed()
            self._outstanding = false

class RelayListener(LazySaver.LazySaver):
    """
    The policy of this listener is like this:

    You keep a list of N preferred relay servers.  Every five minutes you "go shopping", fetch a list of relay servers, handicap them, and insert the winner as the 0th element in your list of preferred relay servers.  This pushes the previous top relayer down to being your second-favorite and so on (unless of course your previous top *is* the new winner of the handicapping in which case there's no change).  (Also, if you get a transaction failure with your current preferred relayer then you go shopping.)

    You poll your preferred relay server every 60 seconds, your second-most-preferred relay server every 120 seconds, and your third-most-preferred every 240 seconds.

    Anytime you receive a message from any relayer, then you schedule a poll for 60 seconds later to that relayer.

    Finally, whenever you receive a message from any relayer then there is a 50% chance that the relayer will get "promoted".  Being promoted means, if you are already in the preferredrelayers list, that you swap places with the relayer above you, and if you are not already in the preferred relayers list, that you get inserted in the middle of the list (thus pushing the least preferred one right off the list).

    This means that you switch your preferred relay server any time that handicapping shows there is a better one, but we have add a "stick with what works" handicapper to try to dampen any churn of switching between relayers (by giving a 500 point handicap to any counterparty that isn't our current preferred relay server.

    Things to do:
    * fix up and tune latency handicap (just use the dynamic-timers statistics instead of gathering separate ones) and reliability handicap
    """
    def __init__(self, mtm, discoveryman=None, neverpoll=false):
        """
        @param neverpoll `true' if you want to override the confman['POLL_RELAYER'] and force it to false;  This is for the Payment MTM -- otherwise you should just use confman.

        @precondition `discoveryman' must be an instance of interfaces.IDiscoveryManager.: isinstance(discoveryman, IDiscoveryManager): "discoveryman: %s :: %s" % (hr(discoveryman), hr(type(discoveryman)),)
        """
        assert isinstance(discoveryman, IDiscoveryManager), "precondition: `discoveryman' must be an instance of interfaces.IDiscoveryManager." + " -- " + "discoveryman: %s :: %s" % (hr(discoveryman), hr(type(discoveryman)),)

        self._mtm = mtm
        self._islistening = false
        self._upward_inmsg_handler = None
        self._neverpoll = neverpoll
        self._regularshoppingison = false
        self._outstandingshoppingtrips = 0 # the number of shopping trips either scheduled on the DoQ, or else outstanding but not yet late
        self._discoveryman = discoveryman

        # A list of relayers that we like, in descending order of preference.
        # self._preferredrelayers = [] # persistent -- it gets initialized only once in the persistent life of the broker -- not every time the broker process is started.  So don't comment this back in, it is just here for documetary purposes.

        # A map from relayer id to the time (approximate!) of the next scheduled poll, if any.  (Use this in order to avoid scheduling multiple polls at once.)
        self._nextscheduledpolls = {}

        LazySaver.LazySaver.__init__(self, fname=os.path.join(self._mtm._dbdir, 'RelayListener.pickle'), attrs={'_preferredrelayers': []}, DELAY=10*60)

        # Tidy up, because some old version might have put bad stuff in the persistent data:
        for thing in self._preferredrelayers:
            if not idlib.is_binary_id(thing):
                self._preferredrelayers.remove(thing)

    def _launch_polling_of_preferred_relayers(self):
        for i in range(len(self._preferredrelayers)):
            self._schedule_poll(self._preferredrelayers[i], delay=(MIN_POLL_DELAY * (2**i) - MIN_POLL_DELAY))

    def shutdown(self):
        LazySaver.LazySaver.shutdown(self)

    def start_listening(self, inmsg_handler_func):
        """
        @precondition `inmsg_handler_func' must be callable.: callable(inmsg_handler_func): "inmsg_handler_func: %s :: %s" % (hr(inmsg_handler_func), hr(type(inmsg_handler_func)),)
        """
        assert callable(inmsg_handler_func), "precondition: `inmsg_handler_func' must be callable." + " -- " + "inmsg_handler_func: %s :: %s" % (hr(inmsg_handler_func), hr(type(inmsg_handler_func)),)

        debugprint("start_listening()\n", v=1, vs='RelayListener')

        self._upward_inmsg_handler = inmsg_handler_func
        self._islistening = true

        self._mtm.add_handler_funcs({'message for you': self._handle_message_for_you})

        self._launch_polling_of_preferred_relayers()
        if not self._regularshoppingison:
            self._regularshoppingison = true
            self._shop_for_better_relayers_doq_loop()

    def stop_listening(self):
        self._islistening = false
        pass

    def is_listening(self):
        return self._islistening

    def _active_polling(self):
        return (not self._neverpoll) and self._mtm._listenermanager.primary_comm_strat_is_relay()

    def _handle_result_of_poll(self, widget, outcome, failure_reason=None, timer=timeutil.timer):
        relayerid = widget.get_counterparty_id()

        # If this was a failure, and the failing relayer is our currently announced one, then go shopping for a new one.  (Note that the new favorite might be the same as the old favorite -- it all depends on handicapping.)
        fav = self._get_favorite()
        if (failure_reason is not None) and idlib.equal(relayerid, fav):
            self._go_shopping()

        # If this is one of our favorites, the let's schedule another poll for them:
        if self._active_polling() and (relayerid in self._preferredrelayers):
            i = self._preferredrelayers.index(relayerid)
            delay = MIN_POLL_DELAY * (2**i)
            self._schedule_poll(relayerid, delay)

    def _get_favorite(self):
        """
        @returns the id of the current favorite or `None' if none.
        """
        if len(self._preferredrelayers) == 0:
            return None
        else:
            return self._preferredrelayers[0]

    def _schedule_poll(self, relayerid, delay, timer=timeutil.timer):
        """
        This does not schedule the poll if there is already a poll scheduled that would go off approximately before this one would.
        (Where approximately is very approximate -- within MIN_POLL_DELAY.)

        @precondition `relayerid' must be an id (in binary form).: idlib.is_binary_id(relayerid): "relayerid: %s :: %s" (hr(relayerid), hr(type(relayerid)),)
        """
        assert idlib.is_binary_id(relayerid), "precondition: `relayerid' must be an id (in binary form)." + " -- " + "relayerid: %s :: %s" % (hr(relayerid), hr(type(relayerid)),)

        approxschedtime = timer.time() + delay
        next = self._nextscheduledpolls.get(relayerid)
        if (next is not None) and (approxschedtime + MIN_POLL_DELAY >= next):
            return

        schedtime = DoQ.doq.add_task(self._retrieve_messages, args=(relayerid,), delay=delay)

        if (next is None) or (schedtime < next):
            self._nextscheduledpolls[relayerid] = schedtime

    def _adopt_new_favorite(self, true=true):
        """
        @precondition The `self._preferredrelayers' list has already been adjusted so that the new favorite is in front.: true
        @precondition The `self._preferredrelayers' list contains at least one element, which is an id.: (len(self._preferredrelayers) > 0) and (idlib.is_binary_id(self._preferredrelayers[0]))
        """
        assert true, "precondition: The `self._preferredrelayers' list has already been adjusted so that the new favorite is in front."
        assert (len(self._preferredrelayers) > 0) and (idlib.is_binary_id(self._preferredrelayers[0])), "precondition: The `self._preferredrelayers' list contains at least one element, which is an id."

        debugprint("%s._adopt_new_favorite(): self._preferredrelayers: %s\n", args=(self, self._preferredrelayers,), v=5, vs="RelayListener")

        # We've changed our favorite -- the one that we advertise.

        # Poll our new favorite.
        self._schedule_poll(self._preferredrelayers[0], 0)

        # Announce our new contact info to the world.
        self._mtm.send_hello_to_meta_trackers()

    def _handle_result_of_shopping(self, outcome, timer=timeutil.timer):
        if outcome is None:
            outcome = {}

        oldbest = self._get_favorite()

        best = self._mtm.get_handicapper().pick_best_from_dict(outcome, "are there messages", {})
        assert (best is None) or idlib.is_binary_id(best), "best: %s :: %s" (hr(best), hr(type(best)),)
        if best is None:
            debugprint("Couldn't find any relayers while shopping.  Will try again later...\n", v=2, vs="debug")
            return

        if idlib.equal(oldbest, best):
            # Oh -- our current favorite is still the best.  Nevermind then.
            return

        if best in self._preferredrelayers:
            self._preferredrelayers.remove(best)

        self._preferredrelayers.insert(0, best)

        del self._preferredrelayers[NUM_PREFERRED_RELAYERS:]
        self._adopt_new_favorite()
        self._lazy_save()

    def _handle_result_of_regularly_scheduled_shopping(self, outcome, timer=timeutil.timer):
        try:
            self._handle_result_of_shopping(outcome)
        finally:
            # This is a DoQ-loop that does `self._shop_for_better_relayers_doq_loop()' every 5 minutes or so.
            DoQ.doq.add_task(self._shop_for_better_relayers_doq_loop, delay=RELAYER_SHOPPING_DELAY)

    def _go_shopping(self):
        self._discoveryman.discover({'type': "Node", 'subtype': "relay server"}, discoveryhand=ShoppingResultsHand(self))

    def _schedule_shopping_trip_if_needed(self):
        assert self._outstandingshoppingtrips >= 0
        if self._outstandingshoppingtrips == 0:
            DoQ.doq.add_task(self._shop_for_better_relayers_doq_loop, delay=RELAYER_SHOPPING_DELAY)

    def _shop_for_better_relayers_doq_loop(self):
        if self._active_polling():
            # The new way -- a separate object called a "discovery man" that can implement any kind of discovery.
            self._discoveryman.discover({'type': "Node", 'subtype': "relay server"}, discoveryhand=ShoppingResultsHand(self))
        else:
            # Oh -- we aren't actively polling a relayer so don't shop for one either.
            # But check again in a few minutes in case we are actively polling then...
            DoQ.doq.add_task(self._shop_for_better_relayers_doq_loop, delay=RELAYER_SHOPPING_DELAY)
            return

    def get_comm_strategy(self):
        fav = self._get_favorite()
        if fav is None:
            return None
        assert idlib.is_binary_id(fav), "self._preferredrelayers: %s" % hr(self._preferredrelayers)
        return CommStrat.Relay(fav, broker_id=self._mtm.get_id(), mtm=self._mtm)

    def compute_handicap_prefer_current(self, counterparty_id, metainfo, message_type, message_body, STICK_WITH_CURRENT_RELAYER_TUNING_FACTOR=STICK_WITH_CURRENT_RELAYER_TUNING_FACTOR):
        fav = self._get_favorite()
        if not idlib.equal(counterparty_id, fav):
            return STICK_WITH_CURRENT_RELAYER_TUNING_FACTOR
        else:
            return 0.0

    def _promote_relayer(self, relayerid):
        """
        This probabilistically increments the relayer's status in our preferredrelayers list (or adds him in if he isn't already there) and calls `_adopt_new_favorite()' if he reaches the top spot.

        @precondition `relayerid' must be an id (in binary form).: idlib.is_binary_id(relayerid): "relayerid: %s :: %s" (hr(relayerid), hr(type(relayerid)),)
        """
        assert idlib.is_binary_id(relayerid), "precondition: `relayerid' must be an id (in binary form)." + " -- " + "relayerid: %s :: %s" (hr(relayerid), hr(type(relayerid)),)

        if ord(randsource.get(1)) < 128:
            # 50% chance
            # If this relayer is on our preferred list, promote him one.
            if relayerid in self._preferredrelayers:
                i = self._preferredrelayers.index(relayerid)
                if i > 0:
                    debugprint("%s._promote_relayer(%s) new rank: %s\n", args=(self, relayerid, i-1,), v=5, vs="RelayListener")
                    self._preferredrelayers[i] = self._preferredrelayers[i-1]
                    self._preferredrelayers[i-1] = relayerid
                    if i == 1:
                        self._adopt_new_favorite()
            else:
                debugprint("%s._promote_relayer(%s) new rank: %s\n", args=(self, relayerid, NUM_PREFERRED_RELAYERS/2,), v=5, vs="RelayListener")
                self._preferredrelayers.insert(NUM_PREFERRED_RELAYERS/2, relayerid)
                del self._preferredrelayers[NUM_PREFERRED_RELAYERS:]
                if len(self._preferredrelayers) == 1:
                    self._adopt_new_favorite()
            self._lazy_save()

    def _inmsg_handler(self, relayerid, msg, timer=timeutil.timer):
        """
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        @precondition `self._upward_inmsg_handler' must be callable.: callable(self._upward_inmsg_handler): "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."
        assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (hr(self._upward_inmsg_handler), hr(type(self._upward_inmsg_handler)),)

        self._upward_inmsg_handler(msg, lowerstrategy=None, strategy_id_for_debug=None)

        self._promote_relayer(relayerid)

        self._schedule_poll(relayerid, MIN_POLL_DELAY)

    def _handle_bundled_messages(self, widget, outcome, failure_reason=None):
        try:
            DataTypes.check_template(outcome, OurMessages.BUNDLED_MESSAGES_TEMPL)
        except MojoMessage.BadFormatError, le:
            debugprint("BadFormatError: %s, stack[-4:]: %s\n", args=(le, traceback.extract_stack()[-4:],), v=0, vs="debug")
            raise le

        if type(outcome) is types.DictType:
            for key in ('messages', 'messages attached', 'messages attached v2',):
                if outcome.has_key(key):
                    outcome = outcome.get(key)
                    break

        for i in outcome:
            if type(i) is types.DictType:
                i = i.get('message')

            self._inmsg_handler(widget.get_counterparty_id(), i)

    def _handle_message_for_you(self, widget, msgbody):
        if type(msgbody) is types.DictType:
            msgbody = msgbody.get('message')
        self._inmsg_handler(widget.get_counterparty_id(), msgbody)
        return {'result': "success"}

    def _handle_retrieve_messages_response(self, widget, outcome, failure_reason=None):
        if failure_reason is not None:
            self._handle_result_of_poll(widget=widget, outcome=None, failure_reason=failure_reason)
            return

        if (type(outcome) in (types.TupleType, types.ListType,)) and (len(outcome) == 2) and CommHints.is_hint(outcome[1]):
            # This is just for a buggy version from CVS that some people checked out in between stable releases.  --Zooko 2001-09-29
            self._handle_retrieve_messages_response(widget, outcome[0])
            return

        self._handle_bundled_messages(widget=widget, outcome=outcome, failure_reason=failure_reason)
        # Got the messages.  We're done with this poll.
        self._handle_result_of_poll(widget=widget, outcome=None, failure_reason=None)
        return

    def _handle_are_there_messages_response(self, widget, outcome, failure_reason=None):
        if failure_reason is not None:
            self._handle_result_of_poll(widget=widget, outcome=None, failure_reason=failure_reason)
            return

        # If it is a new-style (>= 0.995.6) relayer then it might have just sent back all messages that it had for us.
        if type(outcome) in (types.ListType, types.TupleType,):
            if (type(outcome) in (types.TupleType, types.ListType,)) and (len(outcome) == 2) and CommHints.is_hint(outcome[1]):
                # This is just for a buggy version from CVS that some people checked out in between stable releases.  --Zooko 2001-09-29
                self._handle_are_there_messages_response(widget, outcome[0])
                return

            self._handle_bundled_messages(widget=widget, outcome=outcome, failure_reason=failure_reason)
            # Got the messages.  We're done with this poll.
            self._handle_result_of_poll(widget=widget, outcome=None, failure_reason=None)
            return

        if outcome.get('result') == "no":
            # No messages.  We're done with this poll.
            self._handle_result_of_poll(widget=widget, outcome=None, failure_reason=None)
            return

        # This is an old-style relayer that waits for us to actually request the messages and say "please".
        msgbody = {}
        if outcome.get('messages info') is not None:
            msgbody['messages'] = outcome.get('messages info')
        if outcome.get('total bytes') is not None:
            msgbody['bytes'] = outcome.get('total bytes')
        self._mtm.initiate(widget.get_counterparty_id(), 'retrieve messages v2', msgbody, outcome_func=self._handle_retrieve_messages_response, hint=HINT_EXPECT_MORE_TRANSACTIONS)

    def _retrieve_messages(self, relayerid):
        """
        Poll the given relay server once, and retrieve any messages that it has.

        Any messages retrieved will be passed to `self._inmsg_handler()'.

        `self._handle_result_of_poll' will be called one or more times with a `widget' argument whose counterparty id is the id of the relayer and with a `failure_reason' argument.  failure_reason == None means everything went well and we are done.  failure_reason == timeout means that the 97% percentile impatience time has passed, but note that you can still get incoming messages and result-of-poll callbacks, after the "timeout" has passed.

        @precondition `relayerid' must be an id (in binary form).: idlib.is_binary_id(relayerid): "relayerid: %s :: %s" (hr(relayerid), hr(type(relayerid)),)
        """
        assert idlib.is_binary_id(relayerid), "precondition: `relayerid' must be an id (in binary form)." + " -- " + "relayerid: %s :: %s" (hr(relayerid), hr(type(relayerid)),)

        dictutil.del_if_present(self._nextscheduledpolls, relayerid)

        # `'response version': 3' means just shoot back the messages, please, as a list of strings.
        # `'enable fast relay: 1' is unnecessary nowadays, but let's leave it in for one last "backwards compatible withour grandfathers" cycle...  --Zooko 2001-09-04
        # we don't use a dynamic timeout because polling when things are idle causes the timeout to
        # become super low which instantly fails us over to a new relay server when we become busy.
        self._mtm.initiate(relayerid, "are there messages v2", {'response version': 3, 'enable fast relay': 1}, outcome_func=self._handle_are_there_messages_response, post_timeout_outcome_func=self._handle_are_there_messages_response, use_dynamic_timeout="never", timeout=max(5, int(confman['RELAY_SERVER_POLL_TIMEOUT'])), hint=HINT_EXPECT_MORE_TRANSACTIONS)





# Generic stuff
NAME_OF_THIS_MODULE="RelayListener"

mojo_test_flag = true

def run():
    confman['MAX_VERBOSITY'] = "9"
    import RunTests
    RunTests.runTests(NAME_OF_THIS_MODULE)

#### this runs if you import this module by itself
if __name__ == '__main__':
    run()

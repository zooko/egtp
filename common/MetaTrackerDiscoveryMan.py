#!/usr/bin/env python
#
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: MetaTrackerDiscoveryMan.py,v 1.3 2002/07/16 21:07:23 zooko Exp $'


# standard modules
import types

# pyutil modules
import DoQ
from humanreadable import hr

# Mojo Nation modules
import MetaTrackerLib

# EGTP modules
from interfaces import *


class MetaTrackerDiscoveryMan(IDiscoveryMan):
    def __init__(self):
        pass

    def init(self, mtm):
        """
        We would just pass `mtm' to the constructor, but the problem is that the MTM might require a discoveryman in *its* constructor.  Circular constructor dependency.  Oh well.
        """
        self._mtm = mtm

    def discover(self, query, discoverhand):
        def handler_func(widget, outcome, failure_reason=None, discoverhand=discoverhand):
            if outcome is None:
                outcome = {}
            discoverhand.result(outcome)

        # `key' should be a dict with two entries, one with key 'type' and value "Node", and the other with key 'subtype' and value is one of "relay server", etc.
        if (key.get('type') == "Node") and (key.get('subtype') == "relay server"):
            MetaTrackerLib.get_relay_servers_and_call_back(self._mtm, handler_func)
        else:
            raise NotImplementedError # currently don't know how to discover anything other than relay servers

    def publish(self, metadata, object):
        MetaTrackerLib.stuff_hello_into_cache_for_testing(object)

        # Announce yourself to a few of the MT's, randomly chosen.
        mts = mojoutil.rotatelist(MetaTrackerLib.find_root_meta_trackers(self._mtm))

        # How many?  log_base_2 of the number of MTs, plus 1.  That means the following map from num MTs to num to hello: { 1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3, 7: 3, 8: 4, 16: 5, 32: 6, 64: 7, 128: 8, 256: 9, 512: 10 }
        numtohello = mojoutil.int_log_base_2(len(mts)) + 1

        self._metatrackers_sent_hello = mts[:numtohello]
        for (metatracker_id, metatracker_info) in mts[:numtohello]:
            if idlib.equal(self.get_id(), metatracker_id):
                # don't announce self to self, that gets weird. (???)
                continue
            self.initiate(counterparty_id=metatracker_id, conversationtype='hello', firstmsgbody=object)

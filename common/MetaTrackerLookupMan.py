#!/usr/bin/env python
#
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: MetaTrackerLookupMan.py,v 1.4 2002/07/16 21:07:23 zooko Exp $'


# standard modules
import types

# pyutil modules
import DoQ
from humanreadable import hr

# Mojo Nation modules
import MetaTrackerLib

# EGTP modules
from interfaces import *


class MetaTrackerLookupMan(ILookupMan):
    def __init__(self):
        pass

    def init(self, mtm):
        """
        We would just pass `mtm' to the constructor, but the problem is that the MTM may well require a lookupman in *its* constructor.  Circular constructor dependency.  Oh well.
        """
        self._mtm = mtm

    def lookup(self, key, lookuphand):
        # The following func is to translate between the old MojoTransaction callback interface and the new ILookupHandler interface.
        def handler_func(widget, outcome, failure_reason=None, lookuphand=lookuphand):
            if failure_reason:
                lookuphand.done(failure_reason=failure_reason)
                return
            if (type(outcome) is not types.DictType) or (outcome.get('result') != 'success'):
                lookuphand.done(failure_reason="got failure message from meta tracker")
                return
            lookuphand.result(outcome)

        # `key' should be a dict with two entries, one with key 'type' and value"`EGTP address", and the other with key 'key' and value is the id.
        MetaTrackerLib.nonblocking_get_contact_info(self._mtm, key['key'], callback=send_orig_msg, timeout=timeout)

    def publish(self, key, object):
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

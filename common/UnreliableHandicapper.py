#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: UnreliableHandicapper.py,v 1.1 2002/01/29 20:07:07 zooko Exp $'

# standard modules
import whrandom

# our modules
import confutils
import debug
from humanreadable import hr
import idlib
import mojoutil

# The most reliable broker is still handicapped this much.
TUNING_FACTOR=float(2**8)

# Extra boost for publication: we want to publish to more reliable servers!!
PUB_TUNING_FACTOR=float(8)

# The least reliable broker is handicapped as much as the furthest-away broker.
MIN_RELIABILITY=TUNING_FACTOR / idlib.Largest_Distance_NativeId_Int_Space

class UnreliableHandicapper:
    def __init__(self, counterparties, our_id):
        self.counterparties = counterparties
        self.our_id = our_id

    def __call__(self, counterparty_id, metainfo, message_type, message_body, TUNING_FACTOR=TUNING_FACTOR):
        """
        for all msgtypes

        @returns XXX
        """
        if idlib.equal(counterparty_id, self.our_id):
            return 0.0  # no handicap for us, we have high self esteem
        else:
            cpty = self.counterparties.get_counterparty_object(counterparty_id)
            reliability = cpty.get_custom_stat("reliability", 1.0)
            if reliability < MIN_RELIABILITY:
                reliability = MIN_RELIABILITY
                cpty.set_reliability(reliability)

        if message_type == "put blob":
            return (TUNING_FACTOR * PUB_TUNING_FACTOR) / reliability
        else:
            return TUNING_FACTOR / reliability

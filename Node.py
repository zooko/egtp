#!/usr/bin/env python
#
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: Node.py,v 1.3 2002/03/13 21:24:31 zooko Exp $'


# standard modules
import types

# pyutil modules
import DoQ
from humanreadable import hr

# Mojo Nation modules
import CommStrat
import MojoMessage
import MojoTransaction
import idlib

true = 1
false = 0

# EGTP module init
def init():
    DoQ.doq.add_task(MojoMessage.init)

class Node:
    def __init__(self, lookupman, discoveryman, allownonrouteableip=false):
        """
        @param allownonrouteableip `true' if you want the Node to ignore the fact that its detected IP address is non-routeable and go ahead and report it as a valid address;  This is for testing, although it might also be useful some day for routing within a LAN.
        """
        self.mtm = MojoTransaction.MojoTransactionManager(lookupman=lookupman, discoveryman=discoveryman, allownonrouteableip=allownonrouteableip)
        self.mtm.start_listening()

    def get_address(self):
        """
        @return the current EGTP address used to contact this Node or `None' if it isn't currently known
        """
        return self.mtm._get_our_hello_msgbody()

    def set_handler_func(self, mtype, handler_func):
        """
        @param mtype a string
        @param handler_func func to be invoked to handle any incoming messages with the `mtype' string in their "message type" field

        @precondition `mtype' must be a string.: type(mtype) is types.StringType: "mtype: %s :: %s" % (hr(mtype), hr(type(mtype)),)
        @precondition `handler_func' must be callable.: callable(handler_func): "handler_func: %s :: %s" % (hr(handler_func), hr(type(handler_func)),)
        """
        assert type(mtype) is types.StringType, "precondition: `mtype' must be a string." + " -- " + "mtype: %s :: %s" % (hr(mtype), hr(type(mtype)),)
        assert callable(handler_func), "precondition: `handler_func' must be callable." + " -- " + "handler_func: %s :: %s" % (hr(handler_func), hr(type(handler_func)),)

        self.mtm.add_handler_funcs({mtype: handler_func})

    def send(self, recipid, mtype, msg, response_handler_func=None):
        """
        @precondition `recipid' must be an id.: idlib.is_id(recipid): "recipid: %s :: %s" % (hr(recipid), hr(type(recipid)),)
        """
        assert idlib.is_id(recipid), "precondition: `recipid' must be an id." + " -- " + "recipid: %s :: %s" % (hr(recipid), hr(type(recipid)),)

        self.mtm.initiate(recipid, mtype, msg, outcome_func=response_handler_func)


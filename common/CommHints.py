#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: CommHints.py,v 1.1 2002/01/29 20:07:06 zooko Exp $'

### standard modules
import types

# The following hints can be passed to `send_msg()' to allow the comms handler to optimize
# usage of the underlying communication system.  A correct comms handler implementation
# could, of course, ignore these hints, and the comms handler should not fail to send a
# message, send it to the wrong counterparty, or otherwise do something incorrect no matter
# what hints are passed.

# This hint means that you expect an immediate response.  For example, the TCPCommsHandler
# holds the connection open after sending until it gets a message on that connection, then
# closes it.  (Unless HINT_EXPECT_MORE_TRANSACTIONS is also passed, in which case see
# below.)
HINT_EXPECT_RESPONSE = 1

# This hint means that you expect to send and receive messages with this counterparty in the
# near future.  (Who knows what that means?  This is just a hint.)   For example, the
# TCPCommsHandler holds the connection open after sending unless it has too many open
# connections, in which case it closes it.
HINT_EXPECT_MORE_TRANSACTIONS = 2

# For example, if both HINT_EXPECT_RESPONSE and HINT_EXPECT_MORE_TRANSACTIONS are passed,
# then the TCPCommsHandler holds the connection open until it receives a message on that
# connection, then reverts to HINT_EXPECT_MORE_TRANSACTIONS -style mode in which it keeps
# the connection open unless it has too many open connections.

# This hint means that you expect no more messages to or from this counterparty.  For
# example, the TCPCommsHandler closes the connection immediately after sending the message.
# If you pass both HINT_EXPECT_NO_MORE_COMMS and one of the previous hints then you are
# silly.
HINT_EXPECT_NO_MORE_COMMS = 4

# This hint means that you are going to send something.  For example, the TCPCommsHandler
# holds open a connection after it receives a query and then closed it after sending the reply.
HINT_EXPECT_TO_RESPOND = 8

# This hint, when passed with a call to `send()' indicates that the message is a response to an
# earlier received query.
HINT_THIS_IS_A_RESPONSE = 16

HINT_NO_HINT = 0

def is_hint(thingie, IntType=types.IntType, LongType=types.LongType):
    if not type(thingie) in (IntType, LongType,):
        return 0 # `false'
    return (thingie >= 0) and (thingie < 32)


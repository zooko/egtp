#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

import mojostd

from DataTypes import UNIQUE_ID, ASCII_ID, ANY, ASCII_ARMORED_DATA, INTEGER, NON_NEGATIVE_INTEGER, MOD_VAL, INTEGER, ListMarker, OptionMarker, NONEMPTY, NOT_PRESENT, STRING, BOOLEAN

# `templs' is a dict from message types to templates that messages of that type must match.
from templs import templs


from OurMessagesCommStrat import *
from OurMessagesPublicKey import *


# `templs' is a dict from message types to templates that messages of that type must match.


templs['do you have blobs'] = {'block id list': ListMarker(UNIQUE_ID), 'do not recurse': OptionMarker("true")}
# Include 'do not recurse: true' when doing block wholesaling.  Else, leave it off.
templs['do you have blobs response'] = ListMarker(UNIQUE_ID)

templs['request blob'] = {'blob id': UNIQUE_ID, 'do not recurse': OptionMarker("true")}
templs['request blob response'] = [{'result': "success", 'data': ANY}, {'result': "failure"}]

templs['put blob'] = {'blob id': UNIQUE_ID, 'data': ANY, 'passalong': OptionMarker(0)}
templs['put blob response'] = {'result': ["success", "failure"]}



IDMASK_TEMPL={'mask': ASCII_ARMORED_DATA, 'bits': NON_NEGATIVE_INTEGER}


# Relay Server messages
#
MT=[{'message': STRING}, STRING] # An "MT" is either a string (preferred new form) or a dict with key 'message' and value string (deprecated old form).
LMT=[{'messages': ListMarker(MT)}, ListMarker(MT), {'messages attached': ListMarker(MT)}, {'messages attached v2': ListMarker(MT)}] # An "LMT" is either a sequence of MTs (preferred new form) or a dict with key 'messages' and value a sequence of MTs (deprecated old form).
BUNDLED_MESSAGES_TEMPL = LMT

templs['pass this along v2'] = { 'recipient': UNIQUE_ID, 'message': STRING}
templs['pass this along v2 response'] = [{ 'result': "success" }, { 'result': "ok" }, { 'result': "failure", 'reason': STRING }] # XXX It would be nice to change this to be "success" instead of "ok" in order to be consistent with all our other response messages.  I'm writing code from now on that accepts either.  --Zooko 2001-05-05
templs['are there messages v2'] = {'response version': OptionMarker(1)}
templs['are there messages v2 response'] = [
    {'result' : 'no'}, 
    {'result': 'yes', 'number of messages': NON_NEGATIVE_INTEGER, 'total bytes': NON_NEGATIVE_INTEGER, 'messages info': OptionMarker(ListMarker({'sender id': UNIQUE_ID, 'message id': UNIQUE_ID, 'length': 0}))},
    BUNDLED_MESSAGES_TEMPL,
    ListMarker([BUNDLED_MESSAGES_TEMPL, {'result' : 'no'}, {'result': 'yes', 'number of messages': NON_NEGATIVE_INTEGER, 'total bytes': NON_NEGATIVE_INTEGER, 'messages info': OptionMarker(ListMarker({'sender id': UNIQUE_ID, 'message id': UNIQUE_ID, 'length': 0}))}, INTEGER, 0]), # This is just for a buggy version from CVS that some people checked out in between stable releases.  --Zooko 2001-09-29
    ]

templs['retrieve messages v2'] = [{'messages': OptionMarker(ListMarker({'sender id': UNIQUE_ID, 'message id': UNIQUE_ID, 'length': 0}))}]
templs['retrieve messages v2 response'] = [
    {'status': 'no messages'}, 
    BUNDLED_MESSAGES_TEMPL,
    ListMarker([{'status': 'no messages'}, BUNDLED_MESSAGES_TEMPL, INTEGER, 0]), # This is just for a buggy version from CVS that some people checked out in between stable releases.  --Zooko 2001-09-29
    ]

# Let's take the " v2" off of these names...  --Zooko 2001-09-04
for relaymtype in ['pass this along', 'are there messages', 'retrieve messages']:
    templs[relaymtype] = templs[relaymtype + ' v2']
    templs[relaymtype + ' response'] = templs[relaymtype + ' v2 response']

# These are used in fast-relay for a relay server to directly send a message to
# a counterparty down an open connection.
templs['message for you'] = MT
templs['message for you response'] = {'result': ["success", "failure"]}

# Used by content trackers and for talking to content trackers.  data
# is in a content tracker specific format (generally XML or a signed
# SEXP containing XML?)
#
templs['content tracker lookup'] = {'XML data': ANY, 'publicity criterion' :OptionMarker(["public", "private", "both"]), 'first ISO date': OptionMarker(STRING), 'last ISO date': OptionMarker(STRING)}
# 'result' will be either "success" or "failure".  There will be a 'list' field on all "success" responses.
templs['content tracker lookup response'] = {'result': ['success', 'failure', 'no match'], 'list': OptionMarker(ListMarker(STRING)), 'verifier': OptionMarker(["yes", "no"])}
templs['content tracker submit'] = {'XML data': ANY}
templs['content tracker submit response'] = {'result': ['success', 'failure'], 'mojoid': OptionMarker(ASCII_ID)}
templs['download content types'] = {}
templs['download content types response'] = ListMarker(STRING)


# 'hello' and 'hello response' are used for any EGTP agent to contact any other in order to
# establish its id and the connection strategy (i.e. its IP number or whatever).
templs['hello'] = {'connection strategies': ListMarker({}), 'sequence num': 0, 'seconds to live': OptionMarker(0)}
templs['hello response'] = {'result': ["success", "failure"]}
templs['goodbye'] = {}


## BadBlockListSubcriber messages:
templs['get bad block list'] = [
    {}, # The server considers the client a brand new client.
    {'nonce': UNIQUE_ID, # If this doesn't match the server's nonce, the server treats the client as a brand new client (start and end are ignored!)
     'start': OptionMarker(NON_NEGATIVE_INTEGER), # If this is absent, 0 is used.  (The list in the response message has a max size, though.)
     'end': OptionMarker(NON_NEGATIVE_INTEGER), # If this is omitted, the end of the server's list is used.
    }]

templs['get bad block list response'] = [
    {
        'result': 'success',
        'nonce': UNIQUE_ID, # This is always the server's current nonce.  If it doesn't match the clients nonce, the client should notice the discrepancy.
        'start': NON_NEGATIVE_INTEGER, # This is the true starting index on the server side (which might be different than what the client asked for).
        'end': NON_NEGATIVE_INTEGER, # This is the true ending index on the server side (which might be different than what the client asked for).
        'bad block list': ListMarker(UNIQUE_ID), # These are block/blob IDs.
    }, {
        'result': 'failure',
        'failure reason': OptionMarker(STRING),
    }]
# type is one of 'blob server', 'content tracker', 'meta tracker', 'relay server v2'
HELLO_SERVICE_TEMPL={ 'type': STRING }   # don't be explicit here, that would disallow experimental and future services

# These are templates for service descriptions within hello messages
#
HELLO_SERVICE_BLOB_SERVER_TEMPL={ 'type': "blob server", 'publishing allowed': [BOOLEAN, "yes", "no"], 'mask list': OptionMarker(ListMarker(IDMASK_TEMPL)), 'stddev': OptionMarker(NON_NEGATIVE_INTEGER), 'centerpoint': OptionMarker(NON_NEGATIVE_INTEGER)} # We *could* type-check centerpoint more specifically to be >= 0 and < 2**24  --Zooko 2001-07-28 # `publishing allowed' will be required to be BOOLEAN in the future.  For backwards compatibility we are allowing "yes", "no".  --Zooko 2001-07-28
HELLO_SERVICE_META_TRACKER_TEMPL={ 'type': "meta tracker", 'seconds until expiration': NON_NEGATIVE_INTEGER}
HELLO_SERVICE_CONTENT_TRACKER_TEMPL={ 'type': "content tracker", 'content types': OptionMarker(ListMarker(ANY)), 'supports smart queries': OptionMarker('yes')}
HELLO_SERVICE_RELAY_SERVER_TEMPL={ 'type': ["relay server v2", "relay server"]}

####

# The MetaTracker uses this for checking service templates of received hello messages.  If a service type isn't
# a key in this dict, the MetaTracker won't accept it.
#
HELLO_SERVICE_TEMPL_TYPE_MAP = {
    'blob server' : HELLO_SERVICE_BLOB_SERVER_TEMPL,
    'meta tracker' : HELLO_SERVICE_META_TRACKER_TEMPL,
    'content tracker' : HELLO_SERVICE_CONTENT_TRACKER_TEMPL,
    'relay server v2' : HELLO_SERVICE_RELAY_SERVER_TEMPL,
    'relay server' : HELLO_SERVICE_RELAY_SERVER_TEMPL,
}

templs['lookup contact info'] = { 'key id': UNIQUE_ID }

PHONEBOOK_ENTRY = {
    'connection strategies': ListMarker(CRYPTO_COMM_STRAT_TEMPL),
    'services': OptionMarker(ListMarker([ANY, None]))
    }
    # XXX specify the templates for services.  --Zooko 2000-08-01
    # XXXX Greg: is the services value just a list of HELLO_SERVICE_TEMPL_TYPE_MAPS?  --Zooko 2000-08-01
    # We need to leave the ANY in this template for now because the software needs to throw items in the list
    # away on an individual basis rather than the message as a whole within MetaTrackerLib.  Other newer
    # software could be out there advertising a whole new service type that would fail the template check if
    # it weren't for the ANY.  -greg  2000-09-04
    # Example: ListMarker( HELLO_SERVICE_TEMPL_TYPE_MAPS.values() ) will not work into the future as desired
    # because new service types would cause a template check failure. -greg 2000-09-04
    # NOTE: MetaTrackerLib is already intelligently template checking service entries based on their type.

templs['lookup contact info response'] = [
    { 'result': "failure" },
    { 'result': "success",
      'connection strategies': ListMarker(CRYPTO_COMM_STRAT_TEMPL),
      'services': OptionMarker(ListMarker([ANY, None])),
      'sequence num': OptionMarker(0),
      'seconds to live': OptionMarker(0),
    }
    ]

templs['list relay servers v2'] = {}
templs['list relay servers'] = templs['list relay servers v2']
# templs['list relay servers v2 response'] = ListMarker({
#     'connection strategies': ListMarker(CRYPTO_COMM_STRAT_TEMPL),
#     'services': OptionMarker(ListMarker(ANY))})

MOJO_HEADER_OFFER_TEMPL = {'mojo offer': NON_NEGATIVE_INTEGER}

MOJO_HEADER_CREDREJ_TEMPL = {
    'result': "failure",
    'reason': "credit limit reached",
    'price of this service': INTEGER,
    'your credit limit': INTEGER,
    'amount you owe me': INTEGER,
    'min acceptable': INTEGER
    }

MOJO_HEADER_RESP_TEMPL = {
    'amount of offer claimed': NON_NEGATIVE_INTEGER
    }

MOJO_HEADER_RESP_GENERIC_REJECTION_TEMPL = {
    'result': "failure",
    'reason': ANY
    }

# As a matter of fact, mojo offers are currently only valid in initiating messages and the rest are currently only valid in response messages,
# but for convenience, we make a generic template that allows both, here...
MOJO_HEADER_TEMPL = [
    MOJO_HEADER_OFFER_TEMPL,
    MOJO_HEADER_RESP_GENERIC_REJECTION_TEMPL,
    MOJO_HEADER_CREDREJ_TEMPL,
    MOJO_HEADER_RESP_TEMPL
    ]

#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

from DataTypes import UNIQUE_ID, ANY, ASCII_ARMORED_DATA, NON_NEGATIVE_INTEGER, MOD_VAL, INTEGER, ListMarker, OptionMarker

from OurMessagesPublicKey import *

BASE_COMM_STRAT_TEMPL = {
    'broker id': OptionMarker([UNIQUE_ID, None]), # The "or `None'" is for backwards-compatibility -- we have accidentally been storing "Nones" under 'broker id' in the metatracker pickle...  --Zooko 2001-09-02
    'comm strat sequence num': OptionMarker(NON_NEGATIVE_INTEGER),
    }

TCP_COMM_STRAT_TEMPL = {}
TCP_COMM_STRAT_TEMPL.update(BASE_COMM_STRAT_TEMPL)
RELAY_COMM_STRAT_TEMPL = {}
RELAY_COMM_STRAT_TEMPL .update(BASE_COMM_STRAT_TEMPL)
PICKUP_COMM_STRAT_TEMPL = {}
PICKUP_COMM_STRAT_TEMPL .update(BASE_COMM_STRAT_TEMPL)

TCP_COMM_STRAT_TEMPL.update({
    'comm strategy type': "TCP",
    'IP address': ANY,
    'port number': NON_NEGATIVE_INTEGER
    })

RELAY_COMM_STRAT_TEMPL.update({
    'comm strategy type': "relay",
    'relayer id': UNIQUE_ID,
    })

PICKUP_COMM_STRAT_TEMPL.update({
    'comm strategy type': "pickup",
    })

CRYPTO_COMM_STRAT_TEMPL = {
    'comm strategy type': "crypto",
    'pubkey': PKFC_TEMPL,
    'lowerstrategy': [
        TCP_COMM_STRAT_TEMPL,
        RELAY_COMM_STRAT_TEMPL,
        PICKUP_COMM_STRAT_TEMPL,
        ]
    }

COMM_STRAT_TEMPL = [
    CRYPTO_COMM_STRAT_TEMPL,
    TCP_COMM_STRAT_TEMPL,
    RELAY_COMM_STRAT_TEMPL,
    PICKUP_COMM_STRAT_TEMPL,
]
# !!! Zooko: make "IP ADDRESS" template item type.  --Zooko 2000/05/12



#!/usr/bin/env python
#
#  Copyright (c) 2002 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import os

# pyutil modules
# from debugprint import debugprint

# (old-)EGTP modules
import CommStrat
import DataTypes
import LazySaver
from confutils import confman

true = 1
false = None

class ListenerManager(LazySaver.LazySaver):
    """
    Hi!  I'm your friendly neighborhood ListenerManager.  I have a TCP listener and a RelayListener and
    a Crypto listener and I initialize and configure them.  Also I generate "comm strategies" records
    which tell other EGTP nodes how to reach me.  I bump the sequence number of my comm strat
    whenever my listening strategy changes.  That's all.
    """
    def __init__(self,cryptol, tcpl, relayl, mtm, allownonrouteableip=false): 
        """
        @param relaylistener The RelayListener instance which will poll relay servers and unwrap incoming "message for you" messages;  Should not be `None', even if you are not behind a firewall and you are not advertising as "contactable via relay" -- it's always possible that someone out there will send you a "message for you", for one reason or another, and there's no harm in having a relaylistener ready to hear it.
        @param allownonrouteableip `true' if you want the ListenerManager to ignore the fact that its detected IP address is non-routeable and go ahead and report it as a valid comm strategy;  This is for testing, although it might also be useful some day for routing within a LAN.
        """
        self._cryptol = cryptol
        self._tcpl = tcpl
        self._relayl = relayl
        self._mtm = mtm
        self.allownonrouteableip = allownonrouteableip

        # self._commstratseqno = 0 # persistent -- it gets initialized only once in the persistent life of the broker -- not every time the broker process is started.  So don't comment this back in, it is just here for documentary purposes.
        # self._lastannouncedcommstratdict = None # persistent -- it gets initialized only once in the persistent life of the broker -- not every time the broker process is started.  So don't comment this back in, it is just here for documentary purposes.
        LazySaver.LazySaver.__init__(self, fname=os.path.join(self._mtm._dbdir, 'TCPListener.pickle'), attrs={'_commstratseqno': 0, '_lastannouncedcommstratdict': None}, DELAY=10*60)

    def _shutdown_members(self):
        for member in ('_cryptol', '_tcpl', '_relayl',):
            if hasattr(self, member):
                o = getattr(self, member)
                if hasattr(o, 'shutdown'):
                    o.shutdown()
                delattr(self, member)
        self._mtm = None

    def shutdown(self):
        self._shutdown_members()
        LazySaver.LazySaver.shutdown(self)

    def start_listening(self, inmsg_handler_func):
        """
        Okay everybody: START LISTENING!

        Start trying to get incoming messages which you will then pass to `inmsg_handler_func()'.

        If confman.is_true_bool(('POLL_RELAYER',)) or if the TCP listener isn't listening and
        routeable (and you haven't specified `allownonrouteableip'), then tell the relay listener to
        poll relay servers.

        @param inmsg_handler_func the function to be called whenever a message for us comes in
        """
        # things that the cryptol hears get sent up to whoever is above us
        self._cryptol.start_listening(inmsg_handler_func)

        # things that the tcpl hears get sent to the cryptol.
        self._tcpl.start_listening(inmsg_handler_func=self._cryptol.inmsg_handler)

        # things that the relayl hears get sent to the cryptol.
        self._relayl.start_listening(inmsg_handler_func=self._cryptol.inmsg_handler)

    def primary_comm_strat_is_relay(self):
        tcpcs = self._tcpl.get_comm_strategy()
        return confman.is_true_bool(('POLL_RELAYER',)) or (tcpcs is None) or ((not tcpcs.is_routeable()) and not self.allownonrouteableip)

    def get_comm_strategy_and_newflag(self):
        """
        @returns a tuple of (commstrat, newflag) where `newflag' is a boolean indicating whether this comm strat differs from the last one that was returned (persistently)
        """
        result = None
        if self.primary_comm_strat_is_relay():
            llstrat = self._relayl.get_comm_strategy()
            if llstrat is None:
                result = None
            else:
                result = CommStrat.Crypto(pubkey=self._cryptol.get_public_key(), lowerstrategy=llstrat)
        else:
            llstrat = self._tcpl.get_comm_strategy()
            if llstrat is None:
                result = None
            else:
                result = CommStrat.Crypto(pubkey=self._cryptol.get_public_key(), lowerstrategy=llstrat)

        oldstrat = None
        if self._lastannouncedcommstratdict is not None:
            try:
                oldstrat = CommStrat.dict_to_strategy(self._lastannouncedcommstratdict, mtm=self._mtm)
            except DataTypes.BadFormatError:
                # Hm.  Got corrupted in interrupted disk access?
                pass

        if (result is not None) and ((oldstrat is None) or (not result.same(oldstrat))):
            # Announced commstrat has changed.  Bump seqno.
            self._commstratseqno = self._commstratseqno + 1
            # debugprint("ListenerManager.get_comm_strategy_and_newflag(): new comm strat seq no: %s, result: %s, self._lastannouncedcommstratdict: %s, oldstrat: %s, result.same(oldstrat): %s\n", args=(self._commstratseqno, result, self._lastannouncedcommstratdict, oldstrat, result.same(oldstrat),))
            self._lastannouncedcommstratdict = result.to_dict()
            self._lazy_save(delay=0)
            newflag = true
        else:
            newflag = false

        if result is not None:
            result._commstratseqno = self._commstratseqno
            if result._lowerstrategy is not None:
                # Copying the same value into the lowerstrategy is useful because people can compare two lower strategies (with `CommStrat.choose_best_strategy()').
                result._lowerstrategy._commstratseqno = self._commstratseqno

        return (result, newflag,)


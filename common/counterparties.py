#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

#
# This module implements counter party objects used for storing
# information about the various counterparties we've talked to such as
# the amount of mojo offers we've made to them, amount they've made to
# us, their reputation for coming through with their deals in our eyes,
# etc.
#
__cvsid = '$Id: counterparties.py,v 1.2 2002/02/11 00:03:26 zooko Exp $'


# Standard Modules:
from cPickle import dumps, loads, UnpicklingError
import os
import threading
import time
import traceback
import types
import math

# Our Modules:
import Cache
from CleanLogDb import CleanLogDbEnv
import DoQ
true = 1
false = None
from bsddb3 import db, dbobj
import confutils
from confutils import confman
import debug
import fileutil
from humanreadable import hr
import idlib
import mojoutil
from mojoutil import setdefault
import mojosixbit



class CounterpartyObjectKeeper:
    class ExtRes:
        """
        This is for holding things (external resources) that COK needs to finalize after COK is killed.  (post-mortem finalization)
        """
        def __init__(self, db_env, balances_db):
            self.db_env = db_env
            self.balances_db = balances_db

        def __del__(self):
            debug.mojolog.write("%s.__del__(); stack[-6:-1]: %s\n", args=(self, traceback.extract_stack()[-6:-1],), v=5, vs="debug")
            if self.balances_db is not None :
                self.balances_db.close()
                self.balances_db = None
            if self.db_env is not None :
                self.db_env.nosyncerror_txn_checkpoint(0)
                self.db_env.close()
                self.db_env = None

    def __init__(self, dbparentdir, local_id, recoverdb=true) :
        """
        @precondition `local_id' must be an id.: idlib.is_sloppy_id(local_id): "local_id: %s" % hr(local_id)
        """
        assert idlib.is_sloppy_id(local_id), "`local_id' must be an id." + " -- " + "local_id: %s" % hr(local_id)

        local_id = idlib.canonicalize(local_id, "broker")

        db_env = CleanLogDbEnv()
        db_env.set_lk_detect(db.DB_LOCK_DEFAULT)  # enable automatic deadlock detection

        dbdir = os.path.normpath(os.path.join(dbparentdir, idlib.to_ascii(local_id), "cos"))
        fileutil.make_dirs(dbdir)

        self._objcache = Cache.LRUCache(maxsize=64)

        if recoverdb:
            recoverflag = db.DB_RECOVER
        else:
            recoverflag = 0

        # Note: if we want to do multi-processing access to the counterparties db, then we have to turn this off.  Note that turning this flag off causes fatal errors on Win2k.  --Zooko 2000-11-15
        privateflag = db.DB_PRIVATE

        try:
            db_env.open(dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | privateflag | recoverflag)
        except db.DBError, dbe:
            # XXX HACK: sometimes trying again after one recover works
            debug.mojolog.write('Failed to open the database environment the first time, reason: %s\nTrying again...\n', args=(dbe,), vs='CounterpartyObjectKeeper', v=2)
            try:
                db_env.open(dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | db.DB_TXN_NOSYNC | privateflag | recoverflag | db.DB_RECOVER)
            except db.DBError, dbe:
                debug.mojolog.write('Failed to open the database environment the second time, reason: %s\nTrying again...\n', args=(dbe,), vs='CounterpartyObjectKeeper', v=2)
                # XXX DOUBLE CHOCOLATEY HACK sometimes trying *again* after one open *without* DB_RECOVER works.
                db_env.open(dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | db.DB_TXN_NOSYNC | privateflag | recoverflag & (~db.DB_RECOVER))

        db_env.set_flags(db.DB_TXN_NOSYNC, true)

        balances_db = dbobj.DB(db_env)
        balances_db.open('balances', db.DB_BTREE, db.DB_CREATE | db.DB_THREAD )

        self.extres = CounterpartyObjectKeeper.ExtRes(db_env, balances_db)

        self.local_id = local_id

        self.__mos_update_lock = threading.Lock()  # this lock is used for both of the below values
        self.mos_we_owe_others = 0L
        self.mos_others_owe_us = 0L
        self.load_mojooffer_stats()

    def get_counterparty_object(self, counterparty_id) :
        """
        @precondition `counterparty_id' must be a binary id.: idlib.is_binary_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        """
        assert idlib.is_binary_id(counterparty_id), "precondition: `counterparty_id' must be a binary id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)

        if idlib.equal(counterparty_id, self.local_id):
            # we don't try and keep track of mo's or a reputation with ourself
            return SelfCounterpartyObject(counterparty_id, self)

        cobj = self._objcache.get(counterparty_id)
        if cobj is None:
            cobj = CounterpartyObject(counterparty_id, self)
            self._objcache.insert(counterparty_id, cobj)

        return cobj
   
    def get_total_mojo_offer_balance_adjustment(self) :
        """
        Returns the total mojo that we owe or are owed after taking
        all of our credits and debits into account.
        [this could make you think you have lots of mojo if others_owe_us
        is large; you probably don't want to use this in a UI...]
        """
        self.__mos_update_lock.acquire()
        try:
            return self.mos_others_owe_us - self.mos_we_owe_others
        finally:
            self.__mos_update_lock.release()

    def get_total_mojo_we_owe_others(self) :
        """
        Returns the total mojo that we owe others
        """
        return self.mos_we_owe_others
    
    def get_total_mojo_others_owe_us(self) :
        """
        Returns the total mojo that others owe us
        """
        return self.mos_others_owe_us 
    
    def load_mojooffer_stats(self) :
        """
        Called from the constructor.  This looks through the database
        to determine how much we owe or are owed by others initially.
        """
        # debug.mojolog.write("xxx %s.load_mojooffer_stats() stack[-5:-1]: %s\n", args=(self, traceback.extract_stack()[-5:-1],))
        others_owe_us = 0L
        we_owe_others = 0L
        for countarparty_id in self.extres.balances_db.keys() :
            val = CounterpartyObject(countarparty_id, self).get_amount_owe()
            if val > 0 :
                we_owe_others = we_owe_others + val
            else :
                others_owe_us = others_owe_us - val

        self.__mos_update_lock.acquire()
        try:
            self.mos_we_owe_others = we_owe_others
            self.mos_others_owe_us = others_owe_us
        finally:
            self.__mos_update_lock.release()

    def update_mos_we_owe_others_total(self, value) :
        """
        Add value to our known total of mojo offers that we owe others.
        Call with a negative value to decrease the total.
        This should only be called by CounterParty objects.
        """
        self.__mos_update_lock.acquire()
        try:
            self.mos_we_owe_others = self.mos_we_owe_others + value
        finally:
            self.__mos_update_lock.release()

    def update_mos_others_owe_us_total(self, value) :
        """
        @param value how much more they owe us now

        Add value to our known total of mojo offers that other people owe us.
        Call with a negative value to decrease the total.
        This should only be called by CounterParty objects.
        """
        self.__mos_update_lock.acquire()
        try:
            self.mos_others_owe_us = self.mos_others_owe_us + value
        finally:
            self.__mos_update_lock.release()


# Greg's NOTES:
# Store local reputations for each counterparty as:
#    ("number of mojo offers made to counterparty", "related responses received from counterparty")
#
# The difference or ratio can be used to determine if we want to deal
# with a given counterparty again.

# CounterpartyObject database entries are stored keyed on counterparty ids as a pickled dict

class CounterpartyObject :
    """
    Individual counterparty objects are NOT threadsafe
    """
    class ExtRes:
        """
        This is for holding things (external resources) that CO needs to finalize after CO is killed.  (post-mortem finalization)
        """
        def __init__(self):
            pass
        def __del__(self):
            debug.mojolog.write("%s.__del__(); stack[-6:-1]: %s\n", args=(self, traceback.extract_stack()[-6:-1],), v=5, vs="debug")

    def __init__(self, counterparty_id, keeper) :
        """
        @precondition `counterparty_id' must be an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        """
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)

        debug.mojolog.write("%s.__init_(); stack[-6:-1]: %s\n", args=(self, traceback.extract_stack()[-6:-1],), v=5, vs="debug")

        self.extres = CounterpartyObject.ExtRes()

        counterparty_id = idlib.canonicalize(counterparty_id, "broker")

        # amount_will_front: this is the maximum amount that she can owe me before I will refuse to loan her more or perform service for her
        # total_spent: this is the total value in Mojo of services I have ever ordered from her
        # total_performed: this is the total value in Mojo of all services I have ever performed for her
        # balance_transferred_in: the current balance i.e. the difference between the aggregate value in Tokens that I've ever given to her and the aggregate value in Tokens that she's ever given to me; positive means she has given me more Mojo than I have given her
        # num_offers_made: the total number of mojo offers that we have ever sent to her
        # num_offers_good: the total number of request that we have ever sent to her, which were accompanied by mojo offers, and which were satisfied by her

        self._counterparty_id = counterparty_id
        self.keeper = keeper
        self.trans = None

        self._tempawfdelta = 0 # This is used to give a cp a temporary increase which is never written to the persistent db.  (For fast deposits.)

        self._load_from_db()
        # debug.mojolog.write("xxx %s.__init__() stack[-5:-1]: %s\n", args=(self, traceback.extract_stack()[-5:-1],))

    def __repr__(self):
        return "<%s:%s, %x>" % (self.__class__.__name__, hr(self._counterparty_id), id(self),)

    def _debugprint(self, str, reasonstr="", args=(), v=1, vs="counterparty"):
        theseargs=[self._counterparty_id]
        theseargs.extend(list(args))
        if reasonstr:
            reasonstr = " [reason: " + reasonstr + "]"
        debug.mojolog.write("accounting with %s: " + str + reasonstr + "\n", args=theseargs, v=v, vs=vs)

    def _load_from_db(self) :
        """called internally to init the internal variables from the database"""
        try:
            stored = self.keeper.extres.balances_db.get(self._counterparty_id)
        except db.DBError, le:
            debug.mojolog.write("Got error from counterparties db.  Initializing counterparty history to defaults.  counterparty_id: %s, txn: %s, dbflags: %s, le: %s\n", args=(self._counterparty_id, txn, dbflags, le,), v=0, vs="warning")
            stored = None

        if stored is None :
            dict = {}
        else:
            try:
                dict = loads(stored)
            except (UnpicklingError, ValueError,), le:
                debug.mojolog.write("Got error loading counterparties db.  ignoring: %s\n", args=(le,), v=0, vs="warning")
                dict = {}

        # Set _every_ counterparty's AWF to the current DEFAULT_AMOUNT_WILL_FRONT_v3.
        # This changes an old tradition of keeping the AWF separate for each counterparty.
        configged = confman.dict["COUNTERPARTY"].get("DEFAULT_AMOUNT_WILL_FRONT_v3")
        if configged[-1:] == "L":
            configged = configged[:-1]
        try:
            dict['amount will front'] = int(configged)
        except ValueError:
            dict['amount will front'] = long(configged)
          
        if dict.get('total spent') is None :
            dict['total spent'] = 0
        if dict.get('total performed') is None :
            dict['total performed'] = 0
        if dict.get('balance transferred in') is None :
            dict['balance transferred in'] = 0
        if dict.get('num offers made') is None :
            dict['num offers made'] = 0
        if dict.get('num offers good') is None :
            dict['num offers good'] = 0

        self.vals = dict

    def synch(self) :
        assert hasattr(self, 'trans') and (self.trans is None), 'should only call synch once per transaction self: %s, self.__dict__: %s' % (hr(self), hr(self.__dict__))
        self.keeper.extres.db_env.nosyncerror_txn_checkpoint(10)
        self.trans = self.keeper.extres.db_env.txn_begin()
        # debug.mojolog.write("xxx %s.synch() stack[-5:-1]: %s\n", args=(self, traceback.extract_stack()[-5:-1],))

    def save(self, checkpoint=false) :
        assert self.trans is not None, 'should only call save() once'

        newval = dumps(self.vals)
        try:
            self.keeper.extres.balances_db.put(self._counterparty_id, newval, txn=self.trans)
        except db.DBError, le:
            debug.mojolog.write("Got error from counterparties db trying to save.  Ignoring.  counterparty_id: %s, vals: %s, le: %s\n", args=(self._counterparty_id, self.vals, le,), v=0, vs="warning")

        self.trans.commit()
        self.trans = None
        if checkpoint:
            # since we're using DB_TXN_NOSYNC we allow checkpoints to be
            # forced at important times such as when recording an actual
            # token going in our out.
            self.keeper.extres.db_env.nosyncerror_txn_checkpoint(0)

    def done(self) :
        if self.trans is not None :
            self.trans.abort()
            self.trans = None

    def charge(self, amount, reasonstr="") :
        """
        @precondition `amount' is an integer.: type(amount) == types.IntType or type(amount) == types.LongType: "amount: %s :: %s" % (hr(amount), str(type(amount)))
        @precondition `amount' is non-negative.: amount >= 0: "amount: %s" % hr(amount)

        @returns (okay, amount will front, current balance)
        """
        assert type(amount) == types.IntType or type(amount) == types.LongType, "`amount' is an integer." + " -- " + "amount: %s :: %s" % (hr(amount), str(type(amount)))
        assert amount >= 0, "`amount' is non-negative." + " -- " + "amount: %s" % hr(amount)

        self.synch()
        try :
            # This is the amount that you owe me.
            cur_balance = long(self.vals['total performed'] - self.vals['total spent'] - self.vals['balance transferred in'])
            new_balance = long(cur_balance + amount)
            amtwfront = long(self.vals['amount will front']) + self._tempawfdelta

            self._debugprint("counterparties.charge(): amtwfront: %s, self._tempawfdelta: %s\n", args=(amtwfront, self._tempawfdelta,), v=7, vs="accounting")

            # As a special case, it is always ok to charge 0.
            if amount == 0:
                self._debugprint("extending %s credit to her; new_balance = %s", args=(amount, new_balance,), reasonstr=reasonstr)
                return true, amtwfront, new_balance

            if (confman.is_true_bool(['KEEP_FUNCTIONING_WHILE_TS_IS_DOWN'])) or (new_balance <= amtwfront):
                self.keeper.update_mos_others_owe_us_total(amount)  # they owe us more
                self._debugprint("extending %s credit to her. new_balance = %s", args=(amount, new_balance,), reasonstr=reasonstr)
                self.vals['total performed'] = self.vals['total performed'] + amount
                self.save()
                return true, amtwfront, new_balance
            else :
                self._debugprint("XXX amtwfront: %s, cur_balance: %s\n", args=(amtwfront, cur_balance,), reasonstr=reasonstr)
                return false, amtwfront, cur_balance
        finally :
            self.done()

    def get_counterparty_id(self) :
        return self._counterparty_id

    def spend(self, amount, reasonstr="") :
        """
        increment our record of total_spent and our num_offers_made

        @precondition `amount' is an integer.: type(amount) == types.IntType or type(amount) == types.LongType: "amount: %s :: %s" % (hr(amount), str(type(amount)))
        @precondition `amount' is non-negative.: amount >= 0: "amount: %s" % hr(amount)
        """
        assert type(amount) == types.IntType or type(amount) == types.LongType, "`amount' is an integer." + " -- " + "amount: %s :: %s" % (hr(amount), str(type(amount)))
        assert amount >= 0, "`amount' is non-negative." + " -- " + "amount: %s" % hr(amount)

        self.synch()
        try:
            prevtotalspent = self.vals['total spent']
            newtotalspent = prevtotalspent + amount
            self.vals['total spent'] = newtotalspent
            self.keeper.update_mos_we_owe_others_total(amount)  # we owe them more
            self.vals['num offers made'] = self.vals['num offers made'] + 1
            self._debugprint("requesting %s credit from her; total_spent with her = %s" % (amount, self.vals['total spent']), reasonstr=reasonstr)

            self.save()
        finally :
            self.done()

    def unspend(self, amount, reasonstr="") :
        """
        Only call this if you KNOW that your message was never sent (otherwise will torture your loved ones)

        @precondition `amount' is an integer.: type(amount) == types.IntType or type(amount) == types.LongType: "amount: %s :: %s" % (hr(amount), str(type(amount)))
        @precondition `amount' is non-negative.: amount >= 0: "amount: %s" % hr(amount)
        """
        assert type(amount) == types.IntType or type(amount) == types.LongType, "`amount' is an integer." + " -- " + "amount: %s :: %s" % (hr(amount), str(type(amount)))
        assert amount >= 0, "`amount' is non-negative." + " -- " + "amount: %s" % hr(amount)

        self.synch()
        try :
            self.vals['total spent'] = self.vals['total spent'] - amount
            self.keeper.update_mos_we_owe_others_total(0L - amount)  # whoops, take that back!

            # never allow total spent to go negative, that's "weird"; if we unspend() that much, start
            # marking it as services performed for the counterparty and them owing us more.
            if self.vals['total spent'] < 0:
                amount_performed = 0L - self.vals['total spent']
                self.vals['total spent'] = 0L
                self.vals['total performed'] = self.vals['total performed'] + amount_performed
                self.keeper.update_mos_we_owe_others_total(amount_performed)
                self.keeper.update_mos_others_owe_us_total(amount_performed)

            self._debugprint("taking back request for %s credit from her; total_spent (with her) = %s" % (amount, self.vals['total spent']), reasonstr=reasonstr, v=3)
            self.save()
        finally :
            self.done()

    def token_payment_came_in(self, amount, reasonstr=""):
        """
        @param the aggregate value in Mojo of the payment

        @precondition `amount' is an integer.: type(amount) == types.IntType or type(amount) == types.LongType: "amount: %s :: %s" % (hr(amount), str(type(amount)))
        @precondition `amount' is positive.: amount > 0: "amount: %s" % hr(amount)
        """
        assert type(amount) == types.IntType or type(amount) == types.LongType, "`amount' is an integer." + " -- " + "amount: %s :: %s" % (hr(amount), str(type(amount)))
        assert amount > 0, "`amount' is positive." + " -- " + "amount: %s" % hr(amount)
    
        self.synch()
        try :
            self.vals['balance transferred in'] = self.vals['balance transferred in'] + amount
            self.keeper.update_mos_others_owe_us_total(0L - amount)  # they paid up, now they owe us less
            self._debugprint("received tokens worth %s from her; balance_transferred_in (with her) = %s" % (amount, self.vals['balance transferred in']), reasonstr=reasonstr)
            self.save(checkpoint=true)
        finally :
            self.done()

    def token_payment_went_out(self, amount, reasonstr=""):
        """
        @param the aggregate value in Mojo of the payment

        @precondition `amount' is an integer.: type(amount) == types.IntType or type(amount) == types.LongType: "amount: %s :: %s" % (hr(amount), str(type(amount)))
        @precondition `amount' is positive.: amount > 0: "amount: %s" % hr(amount)
        """
        assert type(amount) == types.IntType or type(amount) == types.LongType, "`amount' is an integer." + " -- " + "amount: %s :: %s" % (hr(amount), str(type(amount)))
        assert amount > 0, "`amount' is positive." + " -- " + "amount: %s" % hr(amount)
    
        self.synch()
        try :
            self.vals['balance transferred in'] = self.vals['balance transferred in'] - amount
            self.keeper.update_mos_we_owe_others_total(0L - amount)  # we paid up, now we owe less
            self._debugprint("spent tokens worth %s to her; balance_transferred_in (with her) = %s" % (amount, self.vals['balance transferred in']), reasonstr=reasonstr)
            self.save(checkpoint=true)
        finally :
            self.done()

    def record_spend_success(self) :
        """
        Increment our num_offers_good counter.
        Call this once we've receive a valid response to a MO message we sent earlier
        """
        self.synch()
        try:
            self.vals['num offers good'] = self.vals['num offers good'] + 1
            self.save()
        finally:
            self.done()

    def increment_reliability(self):
        self.update_custom_stat_weighted_sample('reliability', 1)
    def decrement_reliability(self):
        self.update_custom_stat_weighted_sample('reliability', 0)

    
    def update_custom_stat(self, statname, updatefunc, initialvalue):
        """
        Update a custom counterparty reputation statistic with the return value of updatefunc(currentstat).
        The updatefunc is called while holding the counterparty's transaction lock so it needs to be fast.
        (if the statistic doesn't yet exist, initialvalue will be passed to updatefunc).
        """
        self.synch()
        try:
            self.vals[statname] = updatefunc( self.vals.get(statname, initialvalue) )
            self.save()
        finally:
            self.done()

    def update_custom_stat_weighted_sample(self, statname, newvalue, historyweight=None, defaultvalue=0.5):
        """
        @param historyweight 0.0 = ignore history, 1.0 = ignore new sample
        """
        if historyweight is None:
            historyweight = float(confman.dict['COUNTERPARTY'].get('DEFAULT_HISTORY_WEIGHT', 0.75))
        assert (historyweight >= 0) and (historyweight <= 1), "a 0.0 <= historyweight <= 1.0 is required"
        self.synch()
        try:
            stat = self.vals.get(statname)
            if stat is None:
                stat = float(defaultvalue)
            stat = (historyweight * stat) + ((1.0 - historyweight)*newvalue)
            self.vals[statname] = float(stat)
            self.save()
        finally:
            self.done()

    def update_custom_stat_weighted_sample_with_deviation(self, statname, newvalue, historyweight=None,default_value=None):
        """
        @param historyweight 0.0 = ignore history, 1.0 = ignore new sample
        """
        if historyweight is None:
            historyweight = float(confman.dict['COUNTERPARTY'].get('DEFAULT_HISTORY_WEIGHT', 0.75))
        assert (historyweight >= 0) and (historyweight <= 1), "a 0.0 <= historyweight <= 1.0 is required"
        self.synch()
        try:
            stat = self.vals.get(statname)
            self.vals[statname] = mojoutil.update_weighted_sample(stat, newvalue, historyweight)
            self.save()
        finally:
            self.done()
 
    def update_custom_stat_list(self, statname, newitem, maxlen) :
        """
        Update a custom counterparty reputation stored as a list of statistics.  Append newitem to the list
        and make sure the list is not longer than maxlen items long.  This uses update_custom_stat() and is
        a convenience interface as lists of stats are kept quite often.
        If no stat-list of the given name exists, a new one will be created.
        """
        def add_to_list(self, currentlist, newitem=newitem, maxlen=maxlen):
            currentlist.append(newitem)
            currentlist = currentlist[:maxlen]
            return currentlist
        self.update_custom_stat(statname, updatefunc=add_to_list, initialvalue=[])
    
    def delete_custom_stat(self, statname):
        """remove a counterparty statistic (useful for removing old no longer used ones)"""
        if self.vals.has_key(statname):
            self.synch()
            try:
                if self.vals.has_key(statname):  # this could have changed after the synch()
                    del self.vals[statname]
                    self.save()
            finally:
                self.done()

    def get_custom_stat(self, statname, default=None) :
        """
        Return a custom counterparty reputation statistic.
        Returns None if no record of statname exists for this counterparty.
        """
        return self.vals.get(statname, default)

    def set_reliability(self, reliability):
        self.synch()
        try:
            self.vals['reliability'] = float(reliability)
            self.save()
        finally:
            self.done()

    def is_unreliable(self) :
        # Make sure we're up to date w/ whats on the disk
        self.synch()
        try:
            num_made = self.vals['num offers made']
            num_good = self.vals['num offers good']
            assert num_made >= 0 and num_good >= 0
            if num_good > num_made :
                self._debugprint("WARNING: mojo_offers_good is greater than mojo_offers_made. fixing.")
                num_good = num_made
                self.save()
                return 0
            if num_made == num_good :
                # reminder: this also takes care of when they are both zero
                # (we're friendly by default, trusting strangers until they flake on us)
                return 0
            else :
                reliability_percent = float(num_good) / num_made
                size_of_disagreement = num_made - num_good
                if reliability_percent < float(confman.dict["COUNTERPARTY"]["MIN_RESPONSE_RELIABILITY_FRACTION"]) and size_of_disagreement >= int(confman.dict["COUNTERPARTY"]["MIN_NUM_MO_DIFFERENCE_FOR_RELIABILITY_CHECK"]) :
                    return 1  # they're currently unreliable
                if size_of_disagreement >= int(confman.dict["COUNTERPARTY"]["MAX_NUM_MO_DIFFERENCE_BEFORE_UNRELIABLE"]) :
                    return 1  # they're currently unreliable
                return 0
        finally:
            self.done()

    def get_amount_will_front(self) :
        self.synch()
        try :
            # Note: not adding self._tempawfdelta here, because this is only called currently in order to determine if _you_ will front _her_ a coin...
            return self.vals['amount will front']
        finally :
            self.done()

    def raise_temp_awf(self, raiseby):
        self._tempawfdelta = self._tempawfdelta + raiseby

    def lower_temp_awf(self, raiseby):
        self._tempawfdelta = max(self._tempawfdelta - raiseby, 0)

    def get_amount_owe(self) :
        """
        @returns the amount of Mojo that I owe to her
        """
        self.synch()
        try :
            return self.vals['total spent'] - self.vals['total performed'] + self.vals['balance transferred in']
        finally :
            self.done()

    def get_balance_transferred_in(self) :
        """
        @returns the value of all Mojo Token that she has given me;  Negative if I have given her more tokens than she has given me.
        """
        self.synch()
        try :
            return self.vals['balance transferred in']
        finally :
            self.done()


    # called whenever account balance changes to notify 
    # any relevant callbacks        
    def __new_balance(self) :
        pass




class SelfCounterpartyObject(CounterpartyObject):
    """Used as the counterparty for ourselves.  It does nothing.
    We like ourself so much that we don't bother to pay ourself.
    """
    def __init__(self, counterparty_id, keeper) :
        self._counterparty_id = counterparty_id
        self.keeper = keeper
        self.trans = None
        self._tempawfdelta = 0 # This is used to give a cp a temporary increase which is never written to the persistent db.  (For fast deposits.)
    def charge(self, amount, reasonstr="") :
        return true, 1000000000, 0
    def spend(self, amount, reasonstr="") :
        pass
    def unspend(self, amount, reasonstr="") :
        pass
    def record_spend_success(self) :
        pass
    def is_unreliable(self) :
        return 0
    def get_amount_will_front(self) :
        return 10000000000L
    def get_amount_owe(self) :
        return 0
    def token_payment_came_in(self, amount, reasonstr=""):
        return
    def token_payment_went_out(self, amount, reasonstr=""):
        return
    def update_custom_stat(self, statname, updatefunc, initialvalue) :
        updatefunc(initialvalue)
        return
    def update_custom_stat_weighted_sample(self, statname, newvalue, historyweight=None):
        return
    def update_custom_stat_weighted_sample_with_deviation(self, statname, newvalue, historyweight=None,default_value=None):
        return
    def update_custom_stat_list(self, statname, newitem, maxlen) :
        return
    def get_custom_stat(self, statname, default = None) :
        return default


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# This module implements a basic dictionary-like Cache as well
# as an example more advanced StatsCache which can remove items based
# on their access patterns.
#
# $Id: Cache.py,v 1.1 2002/01/29 20:07:06 zooko Exp $

### standard modules
import UserDict
import threading
import time # for tests
import types

### our modules
import Locker
import DoQ
true = 1
false = None
import std
import timeutil

class SimpleCache2(UserDict.UserDict):
    # XXX please add iterators to me.  --Zooko 2001-12-08
    """
    A very simple cache.

    This is really just a wrapper around UserDict that you can subclass, plus some convenient new
    methods.

    `insert()' will be called anytime an item is added to the dict in any way, so if you override
    `insert()' then you can be sure your method will catch any insertion of any items into this
    dict.

    `remove()' will be called for any removal of any items from this dict, including someone calling
    `__delitem__()' or `remove()' or someone calling `insert()' with an extant key and thus
    replacing an object.  Note that if someone calls `insert()' with an extant key and the *same*
    object (as determined with `is') then `remove()' will not be called.

    If you override `insert()' or `remove()', remember to actually add/remove them from self.data,
    or else call `SimpleCache2.insert()' or `SimpleCache2.remove()' respectively.

    `has_key()' will be called anytime a key is tested (including someone calling `has_key()',
    someone calling `__getitem__()', and someone calling `get()' but *not* someone calling `keys()'
    or `items()'.  (The reason to exclude `keys()' and `items()' is that including it would be
    expensive, and that the reason to catch key accesses like this is probably to distinguish
    between keys that are in the cache, which `keys()' or `items()' doesn't do.)

    `get()' will be called anytime an object is fetched from the cache (including someone calling
    `get()' on a key that exists in the cache, someone calling `__getitem__()', but excluding
    someone calling `values()' or `items()', for the same reason as given regards `keys()' above).

    SimpleCache2 assumes single-threaded access.
    """
    def __init__(self, initialdata={}):
        self._mtsafe = false
        self._thread = threading.currentThread()
        UserDict.UserDict.__init__(self, initialdata)

    def __getstate__(self):
        return { 'data': self.data, 'mtsafe': self._mtsafe}

    def __setstate__(self, state):
        self.data = state.get('data', {})
        self._mtsafe = state.get('mtsafe', false)
        self._thread = threading.currentThread()

    def remove(self, key, default=None, strictkey=true):
        """
        remove an item from the cache and return it

        @param strictkey `true' if you want a KeyError in the case that `key' is not there,
            `false' if you want a reference to `default' in the case that `key' is not there
        @param default the object to return if `key' is not there; This is ignored if `strictkey'.
        """
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        item = self.get(key, default)
        if self.has_key(key):
            del self.data[key]
        else:
            if strictkey:
                raise KeyError, key
        return item

    def insert(self, key, item=None):
        """
        @param item if `None', then the key itself is the item

        @return `item'
        """
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        # print "%s.insert(%s, %s)" % (self, key, item,)
        if self.data.has_key(key) and self.data[key] is not item:
            self.remove(key)
        self.data[key] = item
        return item

    def clear(self):
        """
        This is the slow way to do it, to ensure that it calls `remove()' on each method so that subclasses can override `remove()' and catch all exiting keys and values.

        Subclasses would be well-advised to override `remove()' and implement a faster version...
        """
        for k in self.data.keys():
            self.remove(k)

    def get(self, key, default=None, strictkey=false):
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        # It's important to call `self.has_key()' so that subclasses who override `has_key()' can thus learn that this key has been used, even if not `strictkey'.
        # (So don't reverse the order of the following `and' test.)
        if not self.has_key(key) and strictkey:
            raise KeyError, key
        return self.data.get(key, default)

    def has_key(self, key):
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        return self.data.has_key(key)

    def __setitem__(self, key, item):
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        return self.insert(key, item)

    def __delitem__(self, key):
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        return self.remove(key)

    def __getitem__(self, key):
        assert self._mtsafe or self._thread is threading.currentThread(), "self._thread: %s, currentThread(): %s" % (std.hr(self._thread), std.hr(threading.currentThread()),)

        return self.get(key, strictkey=true)

    def update(self, dict):
        for k, v in dict.items():
            self.insert(k, v)

    def setdefault(self, key, failobj=None):
        # `UserDict.setdefault(*)' in Python 2.2 is actually exactly like this, so we wouldn't need to override it at
        # all, but Python 2.1 `UserDict.setdefault()' modifies self.data directly, which we can't allow...
        if not self.has_key(key):
            self[key] = failobj
        return self[key]

    def popitem(self):
        k, v = self.data.popitem()
        # Now put them back...
        self.data[k] = v
        # ... and take them out again so that our subclasses can handle their removal...
        self.remove(k)
        return (k, v,)

class FIFOCache(SimpleCache2):
    """
    A simple first-in-first-out cache.  It keeps a FIFO queue, and when the number of items in the
    cache reaches `maxsize', it removes the oldest item.

    Adding an item that is already in the dict does not change its position in the FIFO queue.
    """
    def __init__(self, maxsize=None, initialdata={}):
        """
        @param maxsize or `None' if there is no max size
        """
        SimpleCache2.__init__(self, initialdata)
        self._fifo = [] # contains keys
        self._maxsize = maxsize
        assert self._assert_invariants()

    def __getstate__(self):
        return { 'SimpleCache2state': SimpleCache2.__getstate__(self), '_fifo': self._fifo, '_maxsize': self._maxsize}

    def __setstate__(self, state):
        SimpleCache2.__setstate__(self, state.get('SimpleCache2state', {}))
        self._fifo = state.get('_fifo', [])
        self._maxsize = state.get('_maxsize', None)

    def _assert_invariants(self):
        assert len(filter(lambda x, sdk=self.data.keys(): x in sdk, self._fifo)) == len(self._fifo), "filter(): %s, len(self._fifo): %s, self._fifo: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, sdk=self.data.keys(): x not in sdk, self._fifo)), std.hr(len(self._fifo)), std.hr(self._fifo), std.hr(len(self.data)), std.hr(self.data),)
        assert len(filter(lambda x, slr=self._fifo: x in slr, self.data.keys())) == len(self.data), "filter(): %s, len(self._fifo): %s, self._fifo: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, slr=self._fifo: x not in slr, self.data.keys())), std.hr(len(self._fifo)), std.hr(self._fifo), std.hr(len(self.data)), std.hr(self.data),)
        assert len(self._fifo) == len(self.data), "filter(): %s, len(self._fifo): %s, self._fifo: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, sdk=self.data.keys(): x not in sdk, self._fifo)), std.hr(len(self._fifo)), std.hr(self._fifo), std.hr(len(self.data)), std.hr(self.data),)
        assert (self._maxsize is None) or (len(self._fifo) <= self._maxsize), "len(self._fifo): %s, self._fifo: %s, self._maxsize: %s" % (std.hr(len(self._fifo)), std.hr(self._fifo), std.hr(self._maxsize),)
        return 1 # `true'
      
    def insert(self, key, item=None):
        assert self._assert_invariants()
        # If this insert is going to increase the size of the cache to bigger than maxsize:
        while (self._maxsize is not None) and (len(self._fifo) >= self._maxsize) and ((not self.data.has_key(key)) or (self.data[key] is not item)):
            self.remove(self._fifo[0])
            assert self._assert_invariants()
        assert self._assert_invariants()
        res = SimpleCache2.insert(self, key, item)
        if not key in self._fifo:
            self._fifo.append(key)
        return res

    def remove(self, key, default=None, strictkey=true):
        assert self._assert_invariants()
        res = SimpleCache2.remove(self, key, default, strictkey)
        if key in self._fifo:
            self._fifo.remove(key)
        assert self._assert_invariants()
        return res

    def clear(self):
        # overridden in order to be faster
        self.data.clear()
        self._fifo= []

    def get_ordered_keys(self):
        assert self._assert_invariants()
        return self._fifo[:]

    def get_first_key(self):
        assert self._assert_invariants()
        return self._fifo[0]

class LRUCache(SimpleCache2):
    """
    A simple least-recently-used cache.  It keeps an LRU queue, and when the number of items in the
    cache reaches `maxsize', it removes the least recently used item.

    Adding an item that is already in the dict *does* make it the most-recently-used item although it
    does not change the state of the dict itself.
    """
    def __init__(self, maxsize=128, initialdata={}):
        SimpleCache2.__init__(self, initialdata)
        self._lru = [] # contains keys
        self._maxsize = maxsize
        assert self._assert_invariants()

    def __getstate__(self):
        return { 'SimpleCache2state': SimpleCache2.__getstate__(self), '_lru': self._lru, '_maxsize': self._maxsize}

    def __setstate__(self, state):
        SimpleCache2.__setstate__(self, state.get('SimpleCache2state', {}))
        self._lru = state.get('_lru', [])
        self._maxsize = state.get('_maxsize', 128)

    def _assert_invariants(self):
        assert len(filter(lambda x, sdk=self.data.keys(): x in sdk, self._lru)) == len(self._lru), "filter(): %s, len(self._lru): %s, self._lru: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, sdk=self.data.keys(): x not in sdk, self._lru)), std.hr(len(self._lru)), std.hr(self._lru), std.hr(len(self.data)), std.hr(self.data),)
        assert len(filter(lambda x, slr=self._lru: x in slr, self.data.keys())) == len(self.data), "filter(): %s, len(self._lru): %s, self._lru: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, slr=self._lru: x not in slr, self.data.keys())), std.hr(len(self._lru)), std.hr(self._lru), std.hr(len(self.data)), std.hr(self.data),)
        assert len(self._lru) == len(self.data), "filter(): %s, len(self._lru): %s, self._lru: %s, len(self.data): %s, self.data: %s" % (std.hr(filter(lambda x, sdk=self.data.keys(): x not in sdk, self._lru)), std.hr(len(self._lru)), std.hr(self._lru), std.hr(len(self.data)), std.hr(self.data),)
        assert len(self._lru) <= self._maxsize, "len(self._lru): %s, self._lru: %s, self._maxsize: %s" % (std.hr(len(self._lru)), std.hr(self._lru), std.hr(self._maxsize),)
        return 1 # `true'
      
    def insert(self, key, item=None):
        assert self._assert_invariants()
        # If this insert is going to increase the size of the cache to bigger than maxsize:
        while (len(self._lru) >= self._maxsize) and ((not self.data.has_key(key)) or (self.data[key] is not item)):
            self.remove(self._lru[0])
            assert self._assert_invariants()
        assert self._assert_invariants()
        res = SimpleCache2.insert(self, key, item)
        if key in self._lru:
            self._lru.remove(key)
        self._lru.append(key)
        return res

    def remove(self, key, default=None, strictkey=true):
        assert self._assert_invariants()
        res = SimpleCache2.remove(self, key, default, strictkey)
        if key in self._lru:
            self._lru.remove(key)
        assert self._assert_invariants()
        return res

    def clear(self):
        # overridden in order to be faster
        self.data.clear()
        self._lru= []

    def has_key(self, key):
        assert self._assert_invariants()
        if self.data.has_key(key):
            assert key in self._lru, "key: %s, self._lru: %s" % (std.hr(key), std.hr(self._lru),)
            self._lru.remove(key)
            self._lru.append(key)
        return SimpleCache2.has_key(self, key)

class LRUCacheLocked(LRUCache, Locker.Locker):
    def __init__(self, maxsize=128, initialdata={}):
        Locker.Locker.__init__(self, mode="blocking")
        LRUCache.__init__(self, maxsize, initialdata)
        self._mtsafe = true

Locker.enable_locker(LRUCacheLocked)

class FIFOCacheLocked(FIFOCache, Locker.Locker):
    def __init__(self, maxsize=None, initialdata={}):
        Locker.Locker.__init__(self, mode="blocking")
        FIFOCache.__init__(self, maxsize, initialdata)
        self._mtsafe = true

Locker.enable_locker(LRUCacheLocked)

class SimpleCache:
    """
    A very simple cache.

    This is really just a wrapper around dicts so that you can subclass them, plus a convenient
    `remove()' method which returns the removed item.

    If you override `insert()' then you can be sure you'll catch any insertion of any items into
    this dict.  If you override `remove()' then you can be sure you'll catch any removal of any
    items from this dict.  Remember to actually add/remove them from self._dict if you do this,
    or else call `SimpleCache.insert()' or `SimpleCache.remove()' respectively.
    """
    def __init__(self):
        self._dict = {}
        self._lock = threading.RLock()

    def remove(self, key, x=None, strictkey=true):
        """
        remove an item from the cache and return it

        @param strictkey `true' if you want a KeyError in the case that `key' is not there,
            `false' if you want a reference to `x' in the case that `key' is not there
        @param x the object to return if `key' is not there; This is ignore if `strictkey'.
        """
        item = self.get(key, x)
        if self.has_key(key):
            del self._dict[key]
        else:
            if strictkey:
                raise KeyError, key
        return item

    def insert(self, key, item=None):
        """
        @param item if `None', then the key itself is the item
        """
        if item:
            self._dict[key] = item
        else:
            self._dict[key] = key

    def __nonzero__(self):
        return self._numitems != 0

    def __len__(self):
        return len(self._dict)

    def __setitem__(self, key, item):
        return self.insert(key, item)

    def keys(self):
        return self._dict.keys()

    def items(self):
        return self._dict.items()

    def values(self):
        return self._dict.values()

    def has_key(self, key):
        return self._dict.has_key(key)

    def get(self, key, x=None):
        return self._dict.get(key, x)

    def __getitem__(self, key):
        return self._dict[key]

    def __delitem__(self, key):
        return self.remove(key)

    
class SimpleStatsCache(SimpleCache):
    """
    A SimpleCache which has most of the guts copied out of StatsCache, except for the part about
    removing things automatically according to a parameterized "throw things out that don't make
    muster" cleaning strategy.  Subclass this in order to implement your favorite cache cleaning
    strategy.

    I left out the size-accounting feature since it is implemented in Cache instead of
    StatsCache and since I don't need it right now.  --Zooko 2000-08-15

    One more difference between this and StatsCache: if you call `values()' or `items()' on
    this, it touches every item, incrementing its usage number.
    """
    def __init__(self):
        SimpleCache.__init__(self)

        self._stats = {}

    def insert(self, key, item=None, timer=timeutil.timer):
        result = SimpleCache.insert(self, key, item)
        now = timer.time()
        self._stats[key] = [now, now, 0]
        return result

    def get(self, key, x=None):
        self._touch(key)
        return SimpleCache.get(self, key, x)

    def remove(self, key, strictkey=true):
        """
        @see SimpleCache for interface documentation
        """
        item = SimpleCache.remove(self, key, strictkey=strictkey)
        try:
            del self._stats[key]
        except KeyError:
            # We do not really care if there are no stats.  If `strictkey', then it is entirely consistent for their to be no stats, and no actual item either!
            pass
        return item

    def items(self):
        """
        This touches (increases the `numaccesses' by 1) all items.
        """
        for key in self._dict.keys():
            self._touch(key)
        return SimpleCache.items()

    def values(self):
        """
        This touches (increases the `numaccesses' by 1) all items.
        """
        for key in self._dict.keys():
            self._touch(key)
        return SimpleCache.values()

    def _touch(self, key, timer=timeutil.timer):
        now = timer.time()
        statslist = self._stats.get(key)
        if statslist is None:
            std.mojolog.write("SimpleStatsCache._touch(): no stats for key %s.  Fixing by adding stats now.\n" % `key`)
            statslist = [now, now, 0]

        statslist[1] = now # update access time
        try:
            statslist[2] = statslist[2] + 1 # update numaccesses
        except OverflowError:
            statslist[2] = statslist[2] + 1L # switch to a long

        self._stats[key] = statslist


# Consider using class CacheSingleThreaded instead.
class Cache:
    """Cache([maxsize], [maxitems], [autolen], [initialdict]) - Resource limited object cache
    A Caching dictionary-like object.  A maximum number of items or
    maximum total size of all items may be specified.  Items will be
    removed in FIFO order to make room for new items.

    initialdict contains the items to initialize this Cache object
    with.  They will be inserted in the order that initialdict.items()
    returns them; subject to the cache size limits and removal rules.
    initialdict values must have a valid __len__ method.

    If autolen is true, len() will be called on all inserted items; if
    a TypeError exception is raised itemsize will be used instead.
    """
    def __init__(self, maxsize=None, maxitems=None, autolen=None, initialdict={}) :
        """
        @param maxsize the maximum amount of ram this cache can hold, or `None' if there is no limit;  This cannot be 0.
        @param maxitems the maximum number of items this cache can hold, or `None' if there is no limit;  This cannot be 0.

        @precondition `maxsize' must be positive.: maxsize is None or maxsize > 0: "maxsize: %s" % std.hr(maxsize)
        @precondition `maxitems' must be positive.: maxitems is None or maxitems > 0: "maxitems: %s" % std.hr(maxitems)
        """
        assert maxsize is None or maxsize > 0, "precondition: `maxsize' must be positive." + " -- " + "maxsize: %s" % std.hr(maxsize)
        assert maxitems is None or maxitems > 0, "precondition: `maxitems' must be positive." + " -- " + "maxitems: %s" % std.hr(maxitems)

        assert type(initialdict) == type({})

        self.lock = threading.RLock()

        # dict of tuples of the cached item and its size: (item, itemsize)
        self.cache = {}
        self.fifo = []    # insertion order list of keys
        self.numitems = 0
        self.totalsize = 0

        self.autolen = autolen

        self.maxsize = maxsize
        self.maxitems = maxitems

        # initialize the cache
        for key, value in initialdict.items() :
            self.insert(key, value, len(value))
  
    def __nonzero__(self) :
        return self.numitems != 0
  
    def __len__(self) :
        return len(self.cache)
  
    ####################################################################
    def insert(self, key, item, itemsize=0) :
        """
        insert(key, item, itemsize=0) - insert item into the cache,
        to be retrieved using key.  itemsize should be the size in bytes
        you wish this item to be counted as.

        @precondition Item size must be non-negative.: itemsize >= 0: "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))
        """
        assert itemsize >= 0, "precondition: Item size must be non-negative." + " -- " + "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))

        self.lock.acquire()
        try:
            # if the object already exists in the cache, replace it
            if self.cache.has_key(key) :
                self.remove(key)
            
            if self.autolen :
                try:
                    itemsize = len(item)
                except TypeError:
                    # len() failed, use the original itemsize
                    pass

            # make sure there is space in the cache
            if (self.maxsize is not None) and (self.totalsize + itemsize) > self.maxsize:
                self.makeroomfor(size=itemsize)
            if (self.numitems is not None) and (self.numitems + 1) > self.maxitems:
                self.makeroomfor(numitems=1)

            # insert the item into the cache and update our stats
            self.cache[key] = (item, itemsize)
            self.fifo.append(key)
            self.totalsize = self.totalsize + itemsize
            self.numitems = self.numitems + 1
        finally:
            self.lock.release()

    def __setitem__(self, key, item, itemsize=0) :
        self.insert(key, item, itemsize)


    ####################################################################
    def setdefault(self, key, item, itemsize=0) :
        """
        Performs this atomic operation:
          - If key does not exist in the cache, insert it.
          - Return the value of self[key]

        Compare the return value to your item parameter using "is" to
        determine if the object already existed in the cache or if
        your new one was inserted.
        """
        self.lock.acquire()
        try:
            if self.cache.has_key(key) :   # if self.has_key(key) :
                return self.cache[key][0]  #     return self[key]

            # Calling insert here is important for proper
            # functionality in derived classes.  -greg
            self.insert(key, item, itemsize)

            return self.cache[key][0]      # return self[key]
        finally:
            self.lock.release()
 
    def popitem(self):
        self.lock.acquire()
        try:
            k = self.keys()[0]
            v = self[k][0]
            del self[k]
            return (k, v)
        finally:
            self.lock.release()

    def update(self, otherdict):
        self.lock.acquire()
        try:
            for k, v in otherdict.items():
                self[k] = v
        finally:
            self.lock.release()
        
    ####################################################################
    def keys(self) :
        self.lock.acquire()
        try:
            k = self.cache.keys()
        finally:
            self.lock.release()
        return k

    ####################################################################
    def items(self) :
        self.lock.acquire()
        try:
            i = self.cache.items()
            i = map(lambda a: (a[0], a[1][0]), i)  # remove size info from values
        finally:
            self.lock.release()
        return i

    ####################################################################
    def values(self) :
        self.lock.acquire()
        try:
            v = self.cache.values()
            v = map(lambda a: a[0], v)   # remove size info
        finally:
            self.lock.release()
        return v

    ####################################################################
    def has_key(self, key) :
        """
        has_key(key) - See if an item is in this cache.  This is not
        deterministic if the cache is being accessed by multiple threads
        at once.  Also it is not useful if this is actually a StatsCache,
        because if `has_key()' says that it has it, and then you try to get it with `get()'
        or with the [] operator, it might have been expired and removed, yielding a `None'
        or a KeyError respectively.

        Therefore, I'm adding a warning message.  You probably should not be using this
        method.
        """
        self.lock.acquire()
        try:
            std.mojolog.write("WARNING: using potentially unsafe method: `Cache.has_key()'.\n", vs="debug", v=3)
            return self.cache.has_key(key)
        finally:
            self.lock.release()

    ####################################################################
    def get(self, key, default=None) :
        """get(key) - Lookup an item in the cache, return None if it doesn't exist"""
        self.lock.acquire()
        try:
            itemtuple = self.cache.get(key)
            if itemtuple is None :
                return default
            return itemtuple[0]
        finally:
            self.lock.release()

    def __getitem__(self, key) :
        self.lock.acquire()
        try:
            if self.has_key(key) :
                return self.get(key)
            else :
                raise KeyError, key
        finally:
            self.lock.release()

    ####################################################################
    def remove(self, key) :
        """ remove(key) - Remove an item from the cache (and return it) """
        self.lock.acquire()
        try:
            item = self.cache[key][0]
            self.totalsize = self.totalsize - self.cache[key][1]
            self.numitems = self.numitems - 1
            del self.cache[key]
            self.fifo.remove(key)
        finally:
            self.lock.release()
        return item

    def __delitem__(self, key) :
        self.remove(key)

    ####################################################################
    def makeroomfor(self, size=0, numitems=0) :
        """
        makeroomfor(size=0, numitems=0) -
        Make room in the cache for numitems objects and size bytes.  Raises
        a ValueError exception if either numitems or size is greater than
        their respective maximums for this Cache object.

        @postcondition not self.maxsize or self.totalsize + size < self.maxsize, "There are enough free bytes (if we care about how much memory the cache takes up)"
        @postcondition not self.maxitems or self.numitems + numitems <= self.maxitems, "There are enough free slots (if we care about how many items there are)"
        """
        old_totalsize = self.totalsize
        old_numitems = self.numitems

        if self.maxsize and size > self.maxsize :
            # raise ValueError, "can't make room for more than maxsize"
            size = self.maxsize
        if self.maxitems and numitems > self.maxitems :
            raise ValueError, "can't make room for more than maxitems"

        assert len(self.fifo) == len(self.cache), "cache len != fifo len, impossible"
        self.lock.acquire()
        try:
            # Free up space in the cache
            if self.maxsize :
                # XXX This greedy approach may behave poorly if the
                # size of the items in the cache varies greatly
                # relative to the magnitude of maxsize!
                while self.maxsize - self.totalsize < size:
                    assert (self.totalsize == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                    assert (self.numitems == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                    self.remove(self.fifo[0])
            if self.maxitems :
                while self.maxitems - self.numitems <= numitems:
                    assert (self.totalsize == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                    assert (self.numitems == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                    self.remove(self.fifo[0])
        finally:
            self.lock.release()

        assert not self.maxsize or self.totalsize + size <= self.maxsize
        assert not self.maxitems or self.numitems + numitems <= self.maxitems

    ####################################################################
    # Empty the cache
    ####################################################################
    def empty(self) :
        """ empty() - empty this Cache object """
        self.lock.acquire()
        try:
            self.cache = {}
            self.fifo = []
            self.totalsize = 0
            self.numitems = 0
        finally:
            self.lock.release()
    

class CacheSingleThreaded:
    """Cache([maxsize], [maxitems], [autolen], [initialdict]) - Resource limited object cache
    A Caching dictionary-like object.  A maximum number of items or
    maximum total size of all items may be specified.  Items will be
    removed in FIFO order to make room for new items.

    initialdict contains the items to initialize this Cache object
    with.  They will be inserted in the order that initialdict.items()
    returns them; subject to the cache size limits and removal rules.
    initialdict values must have a valid __len__ method.

    If autolen is true, len() will be called on all inserted items; if
    a TypeError exception is raised itemsize will be used instead.
    """
    def __init__(self, maxsize=None, maxitems=None, autolen=None, initialdict={}) :
        """
        @param maxsize the maximum amount of ram this cache can hold, or `None' if there is no limit;  This cannot be 0.
        @param maxitems the maximum number of items this cache can hold, or `None' if there is no limit;  This cannot be 0.

        @precondition `maxsize' must be positive.: maxsize is None or maxsize > 0: "maxsize: %s" % std.hr(maxsize)
        @precondition `maxitems' must be positive.: maxitems is None or maxitems > 0: "maxitems: %s" % std.hr(maxitems)
        """
        assert maxsize is None or maxsize > 0, "precondition: `maxsize' must be positive." + " -- " + "maxsize: %s" % std.hr(maxsize)
        assert maxitems is None or maxitems > 0, "precondition: `maxitems' must be positive." + " -- " + "maxitems: %s" % std.hr(maxitems)

        assert type(initialdict) == type({})

        # dict of tuples of the cached item and its size: (item, itemsize)
        self.cache = {}
        self.fifo = []    # insertion order list of keys
        self.numitems = 0
        self.totalsize = 0

        self.autolen = autolen

        self.maxsize = maxsize
        self.maxitems = maxitems

        # initialize the cache
        for key, value in initialdict.items() :
            self.insert(key, value, len(value))
  
    def __nonzero__(self) :
        return self.numitems != 0
  
    def __len__(self) :
        return len(self.cache)
  
    def insert(self, key, item, itemsize=0) :
        """
        insert(key, item, itemsize=0) - insert item into the cache,
        to be retrieved using key.  itemsize should be the size in bytes
        you wish this item to be counted as.

        @precondition Item size must be non-negative.: itemsize >= 0: "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))
        """
        assert itemsize >= 0, "precondition: Item size must be non-negative." + " -- " + "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))

        # if the object already exists in the cache, replace it
        if self.cache.has_key(key) :
            self.remove(key)

        if self.autolen :
            try:
                itemsize = len(item)
            except TypeError:
                # len() failed, use the original itemsize
                pass

        # make sure there is space in the cache
        if (self.maxsize is not None) and (self.totalsize + itemsize) > self.maxsize:
            self.makeroomfor(size=itemsize)
        if (self.numitems is not None) and (self.numitems + 1) > self.maxitems:
            self.makeroomfor(numitems=1)

        # insert the item into the cache and update our stats
        self.cache[key] = (item, itemsize)
        self.fifo.append(key)
        self.totalsize = self.totalsize + itemsize
        self.numitems = self.numitems + 1

    def __setitem__(self, key, item, itemsize=0) :
        self.insert(key, item, itemsize)

    def setdefault(self, key, item, itemsize=0) :
        """
        Performs this atomic operation:
          - If key does not exist in the cache, insert it.
          - Return the value of self[key]

        Compare the return value to your item parameter using "is" to
        determine if the object already existed in the cache or if
        your new one was inserted.
        """
        if self.cache.has_key(key) :   # if self.has_key(key) :
            return self.cache[key][0]  #     return self[key]

        # Calling insert here is important for proper
        # functionality in derived classes.  -greg
        self.insert(key, item, itemsize)

        return self.cache[key][0]      # return self[key]
 
    def popitem(self):
        k = self.keys()[0]
        v = self[k][0]
        del self[k]
        return (k, v)

    def update(self, otherdict):
        for k, v in otherdict.items():
            self[k] = v
        
    def keys(self) :
        return self.cache.keys()

    def items(self) :
        i = self.cache.items()
        i = map(lambda a: (a[0], a[1][0]), i)  # remove size info from values
        return i

    def values(self) :
        v = self.cache.values()
        v = map(lambda a: a[0], v)   # remove size info
        return v

    def has_key(self, key) :
        return self.cache.has_key(key)

    def get(self, key, default=None) :
        """
        get(key) - Lookup an item in the cache, return None if it doesn't exist
        """
        itemtuple = self.cache.get(key)
        if itemtuple is None :
            return default
        return itemtuple[0]

    def __getitem__(self, key) :
        if self.has_key(key) :
            return self.get(key)
        else :
            raise KeyError, key

    def remove(self, key) :
        """
        remove(key) - Remove an item from the cache (and return it)
        """
        item = self.cache[key][0]
        self.totalsize = self.totalsize - self.cache[key][1]
        self.numitems = self.numitems - 1
        del self.cache[key]
        self.fifo.remove(key)
        return item

    def __delitem__(self, key) :
        self.remove(key)

    def makeroomfor(self, size=0, numitems=0) :
        """
        makeroomfor(size=0, numitems=0) -
        Make room in the cache for numitems objects and size bytes.  Raises
        a ValueError exception if either numitems or size is greater than
        their respective maximums for this Cache object.

        @postcondition not self.maxsize or self.totalsize + size < self.maxsize, "There are enough free bytes (if we care about how much memory the cache takes up)"
        @postcondition not self.maxitems or self.numitems + numitems <= self.maxitems, "There are enough free slots (if we care about how many items there are)"
        """
        old_totalsize = self.totalsize
        old_numitems = self.numitems

        if self.maxsize and size > self.maxsize :
            # raise ValueError, "can't make room for more than maxsize"
            size = self.maxsize
        if self.maxitems and numitems > self.maxitems :
            raise ValueError, "can't make room for more than maxitems"

        assert len(self.fifo) == len(self.cache), "cache len != fifo len, impossible"
        # Free up space in the cache
        if self.maxsize :
            # XXX This greedy approach may behave poorly if the
            # size of the items in the cache varies greatly
            # relative to the magnitude of maxsize!
            while self.maxsize - self.totalsize < size:
                assert (self.totalsize == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                assert (self.numitems == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                self.remove(self.fifo[0])
        if self.maxitems :
            while self.maxitems - self.numitems <= numitems:
                assert (self.totalsize == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                assert (self.numitems == 0) or (len(self.fifo) > 0), "len(self.fifo): %s,  self.totalsize: %s,  self.numitems: %s, self.maxsize: %s, size: %s" % (std.hr(len(self.fifo)), std.hr(self.totalsize), std.hr(self.numitems), std.hr(self.maxsize), std.hr(size))
                self.remove(self.fifo[0])

        assert not self.maxsize or self.totalsize + size <= self.maxsize
        assert not self.maxitems or self.numitems + numitems <= self.maxitems

    def empty(self) :
        """
        empty() - empty this Cache object
        """
        self.cache = {}
        self.fifo = []
        self.totalsize = 0
        self.numitems = 0


# This Cache keeps statistics for each item in the cache including the
# insert time, last access time, and total number of accesses.  It
# also adds the expire() method [see below] for removing items from
# the cache based on the kept stats.  It is safe for multithreaded use, but
# if you do not need multithreaded use , then consider using
# StatsCacheSingleThreaded instead, which is a bit faster and less likely to
# surprise you.  For example, with a StatsCache,
# you can get the following surprise:
#
# >>> if s.has_key('spam'):
# >>>     spam = s['spam']
# Traceback (innermost last):
#   File "<stdin>", line 1, in ?
# KeyError: spam
#
# because the cache object threw the `spam' entry out (due to it being too old)
# while executing the "spam = s['eggs']" line.  StatsCache
# does things like this even if there is only one thread using it!

class StatsCache(Cache):
    """
    A Cache that keeps insertion and access time statistics
    on each item.  It adds the expire method for removing items based
    on their stats.  Multithreadsafe, and therefore it can surprise you
    sometimes.
    """

    ####################################################################
    def __init__(self, maxsize=None, maxitems=None, autolen=0, initialdict={}, autoexpireinterval=None, autoexpireparams=None, timer=timeutil.timer):
        """
        @param autoexpireinterval is the number of seconds between automatically calling our expire method.
        @param autoexpireparams is a dict of keyword parameters for self.expire() that will be called every autoexpireinterval seconds.
        """
        Cache.__init__(self, maxsize=maxsize, maxitems=maxitems, autolen=autolen, initialdict=initialdict)

        # stats is a dictionary of lists containing:
        # [insert time, last access time, number of accesses]
        self.stats = {}

        self.autoexpireinterval = autoexpireinterval
        self.autoexpireparams = autoexpireparams
        self.last_autoexpire_run = timer.time()
        self.__in_autoexpire = 0

        if self.autoexpireinterval :
            assert (type(self.autoexpireparams) == type({}))
            # verify that autoexpireparams are acceptable to self.expire() now rather than later
            apply(self.expire, (), self.autoexpireparams)


    ####################################################################
    def __auto_expire(self, timer=timeutil.timer):
        """Run expire if it is time, this must be called with self.lock acquired"""
        if self.__in_autoexpire :
            # don't let autoexpire trigger itself
            return
        now = timer.time()
        time_since_last_autoexpire = now - self.last_autoexpire_run
        if self.autoexpireinterval <= time_since_last_autoexpire :
            self.last_autoexpire_run = now
            self.__in_autoexpire = 1
            try:
                apply(self.expire, (), self.autoexpireparams)
            finally:
                self.__in_autoexpire = 0

    ####################################################################
    def insert(self, key, item, itemsize=0, insertion_time_delta=0.0, timer=timeutil.timer):
        """
        @param insertion_time_delta is used to insert an item as if it
        had been inserted at a different time (before of after now).
        Useful for making an expiration time based cache with varying
        expiration times for the items decided upon insertion.
        
        @precondition Item size must be non-negative.: itemsize >= 0: "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))
        """
        assert itemsize >= 0, "precondition: Item size must be non-negative." + " -- " + "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))

        self.lock.acquire()
        try:
            if self.autoexpireinterval :
                self.__auto_expire()
            Cache.insert(self, key, item, itemsize)
            if self.stats.has_key(key) :
                del self.stats[key]
            now = timer.time() + insertion_time_delta
            # (insertion time, accesstime, number of accesses)
            self.stats[key] = [now, now, 0]
        finally:
            self.lock.release()
    
    ####################################################################
    def get_insertion_time(self, key):
        """
        Returns the insertion time of a given key, returns 0 if the key does not exist in the cache.
        """
        self.lock.acquire()
        try:
            return self.stats.get(key, [0])[0]
        finally:
            self.lock.release()

    ####################################################################
    def get(self, key, default=None, timer=timeutil.timer):
        self.lock.acquire()
        try:
            if self.autoexpireinterval :
                self.__auto_expire()
            item = Cache.get(self, key, default)
            if self.stats.has_key(key) :
                self.stats[key][1] = timer.time()             # update access time
                try:
                    self.stats[key][2] = self.stats[key][2] + 1  # update numaccesses
                except OverflowError:
                    self.stats[key][2] = self.stats[key][2] + 1L # switch to a long
        finally:
            self.lock.release()
        return item

    ####################################################################
    def remove(self, key) :
        self.lock.acquire()
        try:
            item = Cache.remove(self, key)
            del self.stats[key]
            if self.autoexpireinterval :
                self.__auto_expire()
        finally:
            self.lock.release()
        return item

    ####################################################################
    def keys(self) :
        if self.autoexpireinterval :
            self.__auto_expire()
        return Cache.keys(self)

    ####################################################################
    def items(self) :
        if self.autoexpireinterval :
            self.__auto_expire()
        return Cache.items(self)

    ####################################################################
    def values(self) :
        if self.autoexpireinterval :
            self.__auto_expire()
        return Cache.values(self)

    ####################################################################
    def expire(self, minaccesses=0, staletime=0, maxage=None, cleanerfunc=None, timer=timeutil.timer):
        """expire(minaccesses=0, staletime=0, maxage=None) :
        Remove all items from the Cache that:
           a) have been accessed less than minaccesses times,
           b) have not been accessed in the past staletime seconds
        or c) are older than maxage seconds

        cleanerfunc (if given) should take a key and value as parameters and return
        a boolean indicating if they should remain in the cache.  It is only called
        on expired key/value pairs. This can be used to perform extra cleanup of
        objects as they are removed, or to veto an object's removal.  If a removal
        is vetoed that object's access time and number of accesses is updated.
        """
        self.lock.acquire()
        now = timer.time()
        try:
            for key in self.stats.keys() :
                if maxage and now - self.stats[key][0] > maxage :        # (c)
                    if cleanerfunc and cleanerfunc(key, self.get(key)) :
                        continue
                    self.remove(key)
                    continue
                if staletime and now - self.stats[key][1] > staletime :  # (b)
                    if cleanerfunc and cleanerfunc(key, self.get(key)) :
                        continue
                    self.remove(key)
                    continue
                if self.stats[key][2] < minaccesses :                    # (a)
                    if cleanerfunc and cleanerfunc(key, self.get(key)) :
                        continue
                    self.remove(key)
        finally:
            self.lock.release()


    ####################################################################
    def empty(self) :
        self.lock.acquire()
        try:
            Cache.empty(self)
            self.stats = {}
        finally:
            self.lock.release()
    

########################################################################


# This Cache keeps statistics for each item in the cache including the
# insert time, last access time, and total number of accesses.  It
# also adds the expire() method [see below] for removing items from
# the cache based on the kept stats.
class StatsCacheSingleThreaded(CacheSingleThreaded):
    """
    A Cache that keeps insertion and access time statistics
    on each item.  It adds the expire method for removing items based
    on their stats.
    """
    def __init__(self, maxsize=None, maxitems=None, autolen=0, initialdict={}, autoexpireinterval=600, autoexpireparams={}):
        """
        NOTE: this class does -NOT- have the same interface as the StatsCache class.  Specifically, it uses the
              DoQ to schedule a call to expire() every autoexpireinterval seconds.  It is not strictly single threaded, it
              is only allowed to be accessed from the DoQ.

        @param autoexpireinterval is the number of seconds between automatically calling our expire method
        @param autoexpireparams is a dict of keyword parameters for self.expire() that will be called every autoexpireinterval seconds.
        """
        CacheSingleThreaded.__init__(self, maxsize=maxsize, maxitems=maxitems, autolen=autolen, initialdict=initialdict)

        # stats is a dictionary of lists containing:
        # [insert time, last access time, number of accesses]
        self.stats = {}

        self.autoexpireinterval = autoexpireinterval
        self.autoexpireparams = autoexpireparams

        if self.autoexpireparams:
            DoQ.doq.add_task(self._auto_expire, kwargs=self.autoexpireparams, delay=self.autoexpireinterval)

    def insert(self, key, item, itemsize=0, insertion_time_delta=0.0, timer=timeutil.timer):
        """
        @param insertion_time_delta is used to insert an item as if it
        had been inserted at a different time (before of after now).
        Useful for making an expiration time based cache with varying
        expiration times for the items decided upon insertion.
        
        @precondition Item size must be non-negative.: itemsize >= 0: "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))
        """
        assert itemsize >= 0, "precondition: Item size must be non-negative." + " -- " + "key: %s, item: %s, itemsize: %s" % (std.hr(key), std.hr(item), std.hr(itemsize))

        CacheSingleThreaded.insert(self, key, item, itemsize)
        if self.stats.has_key(key) :
            del self.stats[key]
        now = timer.time() + insertion_time_delta
        # (insertion time, accesstime, number of accesses)
        self.stats[key] = [now, now, 0]

    def get_insertion_time(self, key):
        """
        Returns the insertion time of a given key, returns 0 if the key does not exist in the cache.
        """
        return self.stats.get(key, [0])[0]

    def get(self, key, default=None, timer=timeutil.timer):
        item = CacheSingleThreaded.get(self, key, default)
        if self.stats.has_key(key) :
            self.stats[key][1] = timer.time()             # update access time
            try:
                self.stats[key][2] = self.stats[key][2] + 1  # update numaccesses
            except OverflowError:
                self.stats[key][2] = self.stats[key][2] + 1L # switch to a long
        return item

    def remove(self, key) :
        item = CacheSingleThreaded.remove(self, key)
        del self.stats[key]
        return item

    def keys(self) :
        return CacheSingleThreaded.keys(self)

    def items(self) :
        return CacheSingleThreaded.items(self)

    def values(self) :
        return CacheSingleThreaded.values(self)

    def _auto_expire(self, minaccesses=0, staletime=0, maxage=None, cleanerfunc=None, timer=timeutil.timer):
        # std.mojolog.write("%s.expire() self.autoexpireinterval: %s\n", args=(self, self.autoexpireinterval,)) # XYZ
        try:
            self.expire(minaccesses, staletime, maxage, cleanerfunc)
        finally:
            # schedule another expire check
            if self.autoexpireparams:
                DoQ.doq.add_task(self._auto_expire, kwargs=self.autoexpireparams, delay=self.autoexpireinterval)

    def expire(self, minaccesses=0, staletime=0, maxage=None, cleanerfunc=None, timer=timeutil.timer):
        """expire(minaccesses=0, staletime=0, maxage=None) :
        Remove all items from the Cache that:
           a) have been accessed less than minaccesses times,
           b) have not been accessed in the past staletime seconds
        or c) are older than maxage seconds

        cleanerfunc (if given) should take a key and value as parameters and return
        a boolean indicating if they should remain in the cache.  It is only called
        on expired key/value pairs. This can be used to perform extra cleanup of
        objects as they are removed, or to veto an object's removal.  If a removal
        is vetoed that object's access time and number of accesses is updated.
        """
        now = timer.time()

        for key in self.stats.keys() :
            if maxage and ((now - self.stats[key][0]) > maxage):        # (c)
                if cleanerfunc and cleanerfunc(key, self.get(key)) :
                    continue
                self.remove(key)
                continue
            if staletime and ((now - self.stats[key][1]) > staletime):  # (b)
                if cleanerfunc and cleanerfunc(key, self.get(key)) :
                    continue
                self.remove(key)
                continue
            if self.stats[key][2] < minaccesses :                    # (a)
                if cleanerfunc and cleanerfunc(key, self.get(key)) :
                    continue
                self.remove(key)

    def empty(self) :
        CacheSingleThreaded.empty(self)
        self.stats = {}
    

########################################################################

def _help_test_empty_lookup(d) :
    assert d.get('spam') is None

def _help_test_key_error(d) :
    try :
        d['spam']
        assert 0
    except KeyError :
        pass

def _help_test_insert_and_get(d) :
    d.insert("spam", "eggs")
    d["spam2"] = "eggs2"
    assert d.get("spam") == "eggs", str(d)
    assert d.get("spam2") == "eggs2"
    assert d["spam"] == "eggs"
    assert d["spam2"] == "eggs2"

def _help_test_insert_and_remove(d):
    d.insert('spam', "eggs")
    x = d.remove('spam')
    assert x == "eggs", "x: %s" % `x`
    
def test_Cache_empty_lookup():
    _help_test_empty_lookup(Cache())

def test_StatsCacheSingleThreaded_empty_lookup():
    _help_test_empty_lookup(StatsCacheSingleThreaded())

def test_SimpleCache_empty_lookup():
    _help_test_empty_lookup(SimpleCache())

def test_Cache_key_error():
    _help_test_key_error(Cache())
    
def test_StatsCacheSingleThreaded_key_error():
    _help_test_key_error(StatsCacheSingleThreaded())
    
def test_SimpleCache_key_error():
    _help_test_key_error(SimpleCache())
    
def test_Cache_insert_and_get():
    _help_test_insert_and_get(Cache())

def test_StatsCacheSingleThreaded_insert_and_get():
    _help_test_insert_and_get(StatsCacheSingleThreaded())

def test_SimpleCache_insert_and_get():
    _help_test_insert_and_get(SimpleCache())

def test_Cache_insert_and_remove():
    _help_test_insert_and_remove(Cache())

def test_StatsCacheSingleThreaded_insert_and_remove():
    _help_test_insert_and_remove(StatsCacheSingleThreaded())

def _help_test_extracted_bound_method(d):
    insmeth = d.insert
    insmeth('spammy', "eggsy")
    assert d.get('spammy') == "eggsy"

def _help_test_extracted_unbound_method(d):
    insumeth = d.__class__.insert
    insumeth(d, 'spammy', "eggsy")
    assert d.get('spammy') == "eggsy"

def _help_test_unbound_method(C, d):
    umeth = C.insert
    umeth(d, 'spammy', "eggsy")
    assert d.get('spammy') == "eggsy"

def test_em_all():
    for cClass in (Cache, StatsCache, SimpleCache, SimpleStatsCache,):
        myCache = cClass()
        # print "myCache, ", myCache
        _help_test_empty_lookup(myCache)
        _help_test_key_error(myCache)
        _help_test_insert_and_get(myCache)
        _help_test_insert_and_remove(myCache)
        _help_test_extracted_bound_method(myCache)
        _help_test_extracted_unbound_method(myCache)
        _help_test_unbound_method(cClass, myCache)

def test_StatsCache_autoexpire() :
    success = 0
    try:
        c = StatsCache(autoexpireinterval=0.5, autoexpireparams={'foo': "bar"})
    except:
        success = 1
    if not success :
        assert 0, "StatsCache didn't reject bad autoexpireparams"
    c = StatsCache(autoexpireinterval=0.5, autoexpireparams={'minaccesses':3})
    c["spam"] = "eggs"
    c["swallow"] = "african"
    w = c["spam"]  # spam 1
    w = c["spam"]  # spam 2
    w = c["spam"]  # spam 3
    x = c.get("swallow") # swallow 1
    assert c.get("swallow") == "african" # swallow 2
    time.sleep(1)
    c.insert("foo", "bar")  # use the cache, trigger an autoexpire run
    assert c.get("spam") == "eggs"  # spam 4
    assert c.get("swallow") == None # swallow 3

def test_StatsCache_expire_cleanerfunc() :
    # basic test of cleanerfunc
    cleaned_items = []
    c = StatsCache()
    c['spam'] = "eggs"
    c['mog'] = "barf"
    time.sleep(0.6)
    assert c['mog'] == "barf"
    c.expire(staletime=0.5, cleanerfunc=lambda k, v, c=cleaned_items: c.append((k,v)) )
    assert not c.has_key('spam')
    assert len(cleaned_items) == 1 and cleaned_items[0] == ('spam', 'eggs')

    # test that cleanerfunc veto's removal
    c['spam'] = "eggs"
    time.sleep(0.5)
    c.expire(staletime=0.1, cleanerfunc=lambda k, v: k == 'mog')
    assert c.has_key('mog')
    assert not c.has_key('spam')


def test_generic() :
    # print "Testing Cache(maxitems=23, maxsize=2600):"
    C = Cache(maxsize=2600, maxitems=23)
    for i in xrange(0,50) :
        C.insert(i, str(i*i), (i%10)*10)
    # print "  after inserting 50 items:",
    # print len(C), "cache entries (", C.totalsize, "`bytes' )"
    for i in xrange(50,100) :
        C.insert(i, str(i*i), i*5)
    # print "  after inserting 50 more `larger' items:",
    # print len(C), "cache entries (", C.totalsize, "`bytes' )"
    # print
    del C

    ### Test StatsCache
    # print "Testing StatsCacheSingleThreaded():"
    S = StatsCacheSingleThreaded()
    # print "  populating cache with items 1..100 & 310:",
    for i in xrange(1,101) :
        S[i] = i*i
    S[310] = 69
    # print "now contains", len(S), "items."

    # print "  Accessing item 11"
    a = S[11]

    # print "  sleeping 2 seconds..."
    time.sleep(2)
    # print "  adding items 101..200:",
    for i in xrange(101,201) :
        S[i] = i*i
    # print "now contains", len(S), "items."

    # print "  Accessing items 22, 105 twice, and 113"
    a = S[22]
    a = S[113]
    a = S[105]
    a = S[105]

    # print "  sleeping 1 more seconds..."
    time.sleep(2)
    # print "  adding items 201..300:",
    for i in xrange(201,301) :
        S[i] = i*i
    # print "now contains", len(S), "items."

    # print "  Accessing items 11 and 224"
    a = S[11]
    a = S[224]

    # print "  sleeping 1 more second..."
    time.sleep(1)
    # print "  adding items 301..400:",
    for i in xrange(301,401) :
        S[i] = i*i
    # print "now contains", len(S), "items."

    # print "  Accessing item 33, 334 twice, 224, and 205"
    a = S[33]
    a = S[334]
    a = S[224]
    a = S[334]
    a = S[205]

    # print " Expiration tests:"
    # print "  items older than 4 seconds...",
    S.expire(maxage=4)
    # print "now contains", len(S), "items."

    # print "  items accessed less than 2 times...",
    S.expire(minaccesses=2)
    # print "now contains", len(S), "items."
    # print S.keys()

    # print "  items not accessed in the last 1 second...",
    S.expire(staletime=1)
    # print "now contains", len(S), "items."
    # print S.keys()

    try:
        worked = 0
        # print "Testing a cache miss on item 11...",
        d = S[11]
    except KeyError:
        # print "Success."
        worked = 1
    if not worked :
        pass
        # print " TEST FAILED!"
    
    # print "\nTests complete"


def test_get_default_on_Cache():
    s = StatsCacheSingleThreaded()
    s['spam'] = 'eggs'
    assert s.get('ham', 69) == 69
    assert s.get('spam', 69) == 'eggs'

def test_Cache_values():
    c = Cache()
    c[3] = 'three'
    c[4] = 'four'
    assert c.values() == ['three', 'four'] or c.values() == ['four', 'three']

def _help_test_clear(C):
    c = C(10)
    c[11] = 11
    c._assert_invariants()
    c.clear()
    c._assert_invariants()
    assert len(c) == 0

def test_LRUCache_clear():
    _help_test_clear(LRUCache)

def test_FIFOCache_clear():
    _help_test_clear(FIFOCache)

def test_LRUCacheLocked_clear():
    _help_test_clear(LRUCacheLocked)

def test_FIFOCacheLocked_clear():
    _help_test_clear(FIFOCacheLocked)

def _help_test_1(C):
    c = C(10)
    c[11] = 11
    c._assert_invariants()
    c[11] = 11
    c._assert_invariants()
    c[11] = 11
    c._assert_invariants()
    c[11] = 11
    c._assert_invariants()

def test_LRUCache_1():
    _help_test_1(LRUCache)

def test_FIFOCache_1():
    _help_test_1(FIFOCache)

def test_LRUCacheLocked_1():
    _help_test_1(LRUCacheLocked)

def test_FIFOCacheLocked_1():
    _help_test_1(FIFOCacheLocked)

def _help_test_2(C):
    c = C(10)
    c[11] = 11
    c._assert_invariants()
    del c[11]
    c._assert_invariants()
    c[11] = 11
    c._assert_invariants()
    c[11] = 11
    c._assert_invariants()
    
def test_LRUCache_2():
    _help_test_2(LRUCache)

def test_FIFOCache_2():
    _help_test_2(FIFOCache)

def test_LRUCacheLocked_2():
    _help_test_2(LRUCacheLocked)

def test_FIFOCacheLocked_2():
    _help_test_2(FIFOCacheLocked)

def _help_test_3(C):
    c = C(10)
    c[11] = 11
    c._assert_invariants()
    c[11] = 12
    c._assert_invariants()
    c[11] = 13
    c._assert_invariants()
    del c[11]
    c._assert_invariants()
    c[11] = 14
    c._assert_invariants()
    c[11] = 15
    c._assert_invariants()
    c[11] = 16
    c._assert_invariants()

def test_LRUCache_3():
    _help_test_3(LRUCache)

def test_FIFOCache_3():
    _help_test_3(FIFOCache)

def test_LRUCacheLocked_3():
    _help_test_3(LRUCacheLocked)

def test_FIFOCacheLocked_3():
    _help_test_3(FIFOCacheLocked)

def _help_test_limited_cache_1(C):
    c = C(10)
    c._assert_invariants()
    for i in xrange(11):
        c._assert_invariants()
        c[i] = i
        c._assert_invariants()
    assert len(c) == 10
    assert 10 in c.values()
    assert 0 not in c.values()

    del c[1]
    c._assert_invariants()
    assert 1 not in c.values()
    assert len(c) == 9
    c[11] = 11
    c._assert_invariants()
    assert len(c) == 10
    assert 1 not in c.values()
    assert 11 in c.values()
    del c[11]
    c._assert_invariants()

    c[11] = 11
    c._assert_invariants()
    assert len(c) == 10
    assert 1 not in c.values()
    assert 11 in c.values()

    c[11] = 11
    c._assert_invariants()
    assert len(c) == 10
    assert 1 not in c.values()
    assert 11 in c.values()

    for i in xrange(200):
        c[i] = i
        c._assert_invariants()
    assert 199 in c.values()
    assert 190 in c.values()

def test_LRUCache_limited_cache_1():
    _help_test_limited_cache_1(LRUCache)

def test_FIFOCache_limited_cache_1():
    _help_test_limited_cache_1(FIFOCache)

def test_LRUCacheLocked_limited_cache_1():
    _help_test_limited_cache_1(LRUCacheLocked)

def test_FIFOCacheLocked_limited_cache_1():
    _help_test_limited_cache_1(FIFOCacheLocked)

def _help_test_limited_LRU_cache_1(C):
    c = C(10)
    c._assert_invariants()
    for i in xrange(11):
        c._assert_invariants()
        c[i] = i
        c._assert_invariants()
    assert len(c) == 10
    assert 10 in c.values()
    assert 0 not in c.values()

    c.has_key(1) # this touches `1' and makes it fresher so that it will live and `2' will die next time we overfill.
    c._assert_invariants()

    c[99] = 99
    c._assert_invariants()
    assert len(c) == 10
    assert 1 in c.values(), "c.values(): %s" % std.hr(c.values(),)
    assert not 2 in c.values()
    assert 99 in c.values()

def test_LRUCache_limited_LRU_cache_1():
    _help_test_limited_LRU_cache_1(LRUCache)

def test_LRUCacheLocked_limited_LRU_cache_1():
    _help_test_limited_LRU_cache_1(LRUCacheLocked)

def _help_test_limited_FIFO_cache_1(C):
    c = C(10)
    c._assert_invariants()
    for i in xrange(11):
        c._assert_invariants()
        c[i] = i
        c._assert_invariants()
    assert len(c) == 10
    assert 10 in c.values()
    assert 0 not in c.values()

    c.has_key(1) # this touches `1', but touching it does not affect its position in the FIFO.
    c._assert_invariants()

    c[99] = 99
    c._assert_invariants()
    assert len(c) == 10, "c.values(): %s" % std.hr(c.values(),)
    assert not 1 in c.values(), "c.values(): %s" % std.hr(c.values(),)
    assert 2 in c.values(), "c.values(): %s" % std.hr(c.values(),)
    assert 99 in c.values(), "c.values(): %s" % std.hr(c.values(),)

def test_FIFOCache_limited_FIFO_cache_1():
    _help_test_limited_FIFO_cache_1(FIFOCache)

def test_FIFOCacheLocked_limited_FIFO_cache_1():
    _help_test_limited_FIFO_cache_1(FIFOCacheLocked)

def help_test_Cache_update(C):
    c = C()
    assert c._assert_invariants()
    c['b'] = 99
    assert c._assert_invariants()
    d={ 'a': 0, 'b': 1, 'c': 2,}
    c.update(d)
    assert c._assert_invariants()
    assert c.get('a') == 0, "c.get('a'): %s" % c.get('a')
    assert c._assert_invariants()
    assert c.get('b') == 1
    assert c._assert_invariants()
    assert c.get('c') == 2
    assert c._assert_invariants()

def test_LRUCache_update():
    help_test_Cache_update(LRUCache)

def test_LRUCacheLocked_update():
    help_test_Cache_update(LRUCacheLocked)

def test_FIFOCache_update():
    help_test_Cache_update(FIFOCache)

def test_FIFOCacheLocked_update():
    help_test_Cache_update(FIFOCacheLocked)

# benchmarking:
##global d
##d={}
##def initfunc(n):
##    global d
##    for i in xrange(n):
##        d[i] = i
##def func(n):
##    s = FIFOCache()
##    global d
##    s.update(d)
## import benchfunc
## bench(func, initfunc, TOPXP=16)

mojo_test_flag = 1

def run():
    import RunTests
    RunTests.runTests('Cache')

if __name__ == '__main__' :
    run()

#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import binascii
import copy
import math
import operator
import os
import profile
import pstats
import re
import sha
import string
import struct
import sys
import threading
import traceback
import time
import types
import whrandom
import random
import zlib

# pyutil modules
from humanreadable import hr
from debugprint import debugprint
import fileutil

# old-EGTP modules
from confutils import confman

try:
    import trace
except ImportError, le:
    debugprint("ignoring failure to import trace. le: %s\n", args=(le,), v=6, vs="debug")
    pass

try:
    import coverage
except ImportError, le:
    debugprint("ignoring failure to import coverage. le: %s\n", args=(le,), v=6, vs="debug")
    pass

# Backwards-compatible names.
from cryptutil import *
from mojosixbit import *
from fileutil import *
from dictutil import *
from canon import *
from mojostd import iso_utc_time, iso_utc_time_to_localseconds, test_iso8601_utc_time, test_iso_utc_time_to_localseconds


def bool(thingie):
    if thingie:
        return 1
    else:
        return None

def get_file_size(f):
    ptr = f.tell()
    f.seek(0, 2)
    try:
        return f.tell()
    finally:
        f.seek(ptr)

def is_machine_little_endian():
    # XXX See sys.byteorder in Python >= 2.0.  --Zooko 2002-01-03
    # This assumes that the `struct' module correctly packs ints in native format.
    if struct.pack("=i", 1)[0] == "\001":
        return true
    else:
        return false

def _skim_with_builtin_naive(set, num):
    """
    very slow
    """
    items = set.items()
    items.sort(lambda a, b: cmp(b[1], a[1]))
    items = items[num:]
    for key, val in items:
        del set[key]
    return

def _skim_with_builtin(set, num):
    """
    nice and fast, but still does a full sort so it is O(N log N)

    @precondition `num' must be non-negative.: num >= 0: "num: %s" % `num`
    """
    assert num >= 0, "precondition: `num' must be non-negative." + " -- " + "num: %s" % `num`

    if len(set) <= num:
        return

    if num == 0:
        set.clear()
        return

    if len(set) == 0:
        return

    vals = set.values()
    vals.sort()

    i = len(vals) - num
    # Now the smallest value that can remain in `set' is in vals[i].
    smallestval = vals[i]

    # Now see how many other elements, with the same value, should be thrown out.
    j = i
    while (i > 0) and (vals[i-1] == smallestval):
        i = i - 1

    numdups = j - i # the number of elements with the same value that must be thrown out.
    numthrown = 0

    # print "i: %s, numdups: %s, vals: %s, smallestval: %s" % (`i`, `numdups`, `vals`, `smallestval`)
    # Now make one pass through `set' throwing out all elements less than val, plus `numdups' of the same val.
    items = set.items()

    for key, val in items:
        if val < smallestval:
            del set[key]
        elif val == smallestval:
            if numthrown < numdups:
                del set[key]
                numthrown = numthrown + 1

    assert len(set) == num, "len(set): %s, num: %s, set: %s" % (`len(set)`, `num`, `set`)

def _skim_with_partial_bisort(set, num):
    """
    Throw out all but the top `num' items.
    This does a partial binary insertion sort.
    This mutates `set'.
    All values must be > (-sys.maxint-1).
    This is up to 2.5 times as fast as `_sort_with_builtin()' in benchmarks.  It's fastest when `num' is small.

    @param set a map from keys to values
    @returns No return value, but `set' has been "skimmed" so that only the `num' items with the highest values remain.
    @precondition `num' must be non-negative.: num >= 0: "num: %s" % hr(num)
    """
    assert num >= 0, "precondition: `num' must be non-negative." + " -- " + "num: %s" % hr(num)

    if len(set) <= num:
        return

    if num == 0:
        set.clear()
        return

    if len(set) == 0:
        return

    # print "set: %s" % `set`
    winkeys = []
    winvals = []
    min = -sys.maxint - 1
    for k, v in set.items():
        assert v > (-sys.maxint - 1)
        if v > min:
            # b["onepass"] = 0
            # startt("onepass")
            # print "k: %s, v: %s" % (`k`, `v`)
            rite = len(winvals)
            left = 0
            while left < rite:
                mid = (left + rite) / 2
                if v > winvals[mid]:
                    rite = mid
                else:
                    left = mid + 1
            winvals.insert(left, v)
            winkeys.insert(left, k)
            if len(winvals) > num:
                del winvals[-1]
                del winkeys[-1]
                min = winvals[-1]
            # stopt("onepass")

    # b["recon"] = 0
    # startt("recon")
    set.clear()
    map(operator.setitem, [set]*len(winvals), winkeys, winvals)
    # stopt("recon")

    assert len(set) == num, "len(set): %s, num: %s, set: %s, winners: %s" % (`len(set)`, `num`, `set`, `winners`)

def _skim_with_partial_qsort(set, num):
    """
    This destroys `set'.

    Throw out all but the top `num' items.

    This does a partial quick-sort which is O(2N) compared to doing a full sort and then keeping the top N, which is O(N log N).

    This is faster than `_skim_with_builtin()', but it is complicated and potentially brittle in the presence of different statistical distributions, weird values of `num', etc.

    @precondition `num' must be non-negative.: num >= 0: "num: %s" % hr(num)
    """
    assert num >= 0, "precondition: `num' must be non-negative." + " -- " + "num: %s" % hr(num)

    if len(set) <= num:
        return

    if num == 0:
        set.clear()
        return

    if len(set) == 0:
        return

    torv = 0 # "throw out radixval";  Must be set to `false' initially, then it toggles when each radixval is hit.  This is to prevent the infinite loop in which you have N elements with all the same value, and you are trying to get K elements; K < N.
    other = None
    while len(set) > num:
        origlenset=len(set)
        ix = 1.0 - float(num) / len(set)
        if (len(set) <= 1024) or ((len(set) <= 65536) and (abs(ix-0.5) < 0.3)):
            _skim_with_builtin(set, num)
            assert len(set) == num, "len(set): %s, num: %s" % (`len(set)`, `num`)
            return

        other = {} # (Throw away previous `other'.)

        items = set.items()

        rs = []
        for i in range(15):
            rs.append(whrandom.choice(items)[1])

        i = int(ix * len(rs))
        if i > 7:
            i = i - 1
        elif i < 7:
            i = i + 1

        assert i < len(rs), "i: %s, rs: %s" % (hr(i), hr(rs))
        assert i >= 0, "i: %s" % hr(i)
        rs.sort()
        radix = rs[i]

        for key, val in items:
            if val < radix:
                other[key] = val
                del set[key]
            elif val == radix:
                if torv:
                    other[key] = val
                    del set[key]
                torv = not torv

    assert len(set) <= num
    assert other is None or (len(other) + len(set) >= num), "len(other): %s, len(set): %s, num: %s" % (`len(other)`, `len(set)`, `num`)

    if (len(set) < num) and (other):
        # If we have too few, skim the top from `other' and move them into `set'.
        _skim_with_partial_qsort(other, num - len(set))
        assert len(other) == (num - len(set)), "len(other): %s, num: %s, len(set): %s" % (`len(other)`, `num`, `len(set)`)
        set.update(other)

    assert len(set) == num, "len(set): %s, num: %s" % (`len(set)`, `num`)
    return

skim = _skim_with_partial_bisort

### >>> please comment me out for distribution -- I am testing and benchmarking code
##BSIZES = []
##for i in range(19-4):
##    BSIZES.append(2**(i+4))

##global _bench_dicts_serred 
##_bench_dicts_serred = None

##global _bench_dicts
##_bench_dicts = {}
##global _bench_dicts_bak
##_bench_dicts_bak = {}

##global FUNCS, FNAMES
### FUNCS = [ skim, _skim_with_builtin, _skim_with_builtin_naive ]
##FUNCS = [ _skim_with_partial_bisort, skim, _skim_with_builtin, _skim_with_builtin_naive  ]
### FUNCS = [ _skim_with_partial_bisort ]
### FNAMES = [ "skim", "_skim_with_builtin", "_skim_with_builtin_naive" ]
##FNAMES = [ "_skim_with_partial_bisort", "skim", "_skim_with_builtin", "_skim_with_builtin_naive" ]
### FNAMES = [ "_skim_with_partial_bisort" ]

##def _help_make_init_func(N):
##    def init(N=N):
##        _help_init_bench_dict(N)
##    return init

##def _help_testemall():
##    i = 0
##    global FUNCS, FNAMES
##    for FUNC in FUNCS:
##        print "FUNC: %s" % FNAMES[i]
##        _help_test_skim_2(FUNC=FUNC)
##        i = i + 1

##def _help_benchemall():
##    import benchfunc

##    global FUNCS, FNAMES
##    global BSIZES
##    for BSIZE in BSIZES:
##        print "BSIZE: %s" % BSIZE
##        for BS2 in BSIZES:
##            if BS2 < BSIZE / 128:
##                print "BS2: %s" % BS2
##                _help_init_bench_dict(BSIZE)
##                IF = _help_make_init_func(BSIZE)
##                i = 0
##                for FUNC in FUNCS:
##                    BF = _help_make_bench_skim(FUNC, BS2)
##                    REPS = ((12 - math.log(max(BSIZE, 16))) ** 2) + 1
##                    # REPS = 1
##                    print "FUNC: %s, REPS: %d" % (FNAMES[i], REPS)
##                    benchfunc.rebenchit(BF, BSIZE, initfunc=IF, REPS=REPS)
##                    i = i + 1

##    global b
##    print b

##def _help_init_first_bench_dict(N):
##    global _bench_dicts
##    global _bench_dicts_bak

##    keys = _bench_dicts_bak.keys()
##    keys.sort()
##    _bench_dicts[N] = {}
##    _bench_dicts_bak[N] = {}

##    if len(keys) > 0:
##        i = keys[-1]
##        _bench_dicts_bak[N].update(_bench_dicts_bak[i])
##    else:
##        i = 0

##    thisdict_bak = _bench_dicts_bak[N]
##    rand = random.lognormvariate
##    # rand = random.normalvariate
##    while i < N:
##        i = i + 1
##        X = rand(0, 1)
##        thisdict_bak[i] = X

##def _help_init_bench_dict(N):
##    global _bench_dicts
##    global _bench_dicts_bak

##    if not _bench_dicts_bak.has_key(N):
##        _help_init_first_bench_dict(N)
##    _bench_dicts[N].update(_bench_dicts_bak[N])

##def _help_make_bench_skim(benchfunc, num):
##    global _bench_dicts
##    global _bench_dicts_bak

##    def f(N, num=num, benchfunc=benchfunc):
##        benchfunc(_bench_dicts[N], num=num)
##    return f
### <<< please comment me out for distribution -- I am testing and benchmarking code

def _help_test_skim(FUNC, SETSIZE, MAXVAL, NUMWANTED):
    whrandom.seed(0,0,0)
    d = {}
    for i in range(SETSIZE):
        d[i] = whrandom.randint(0, MAXVAL)

    db = {}
    db.update(d)

    FUNC(d, NUMWANTED)
    l = d.items()
    l.sort(lambda a, b: cmp(b[1], a[1]))

    l2 = db.items()
    l2.sort(lambda a, b: cmp(b[1], a[1]))
    l2 = l2[:NUMWANTED]

    for i in range(NUMWANTED):
        assert l[i][1] == l2[i][1], "i: %s, l: %s, l2: %s" % (`i`, `l`, `l2`)

def _help_test_skim_2(FUNC):
    _help_test_skim(FUNC, 1, 4, 0)
    _help_test_skim(FUNC, 1, 4, 1)
    _help_test_skim(FUNC, 2, 4, 0)
    _help_test_skim(FUNC, 2, 4, 1)
    _help_test_skim(FUNC, 2, 4, 2)
    _help_test_skim(FUNC, 3, 4, 0)
    _help_test_skim(FUNC, 3, 4, 1)
    _help_test_skim(FUNC, 3, 4, 2)
    _help_test_skim(FUNC, 3, 4, 3)
    _help_test_skim(FUNC, 4, 4, 0)
    _help_test_skim(FUNC, 4, 4, 1)
    _help_test_skim(FUNC, 4, 4, 2)
    _help_test_skim(FUNC, 4, 4, 3)
    _help_test_skim(FUNC, 4, 4, 4)
    _help_test_skim(FUNC, 10, 10, 3)
    _help_test_skim(FUNC, 10, 1000, 3)
    _help_test_skim(FUNC, 30, 4, 10)
    _help_test_skim(FUNC, 100, 10, 30)
    _help_test_skim(FUNC, 100, 1000, 30)
    _help_test_skim(FUNC, 300, 4, 100)
    _help_test_skim(FUNC, 3000, 1000, 100)
    _help_test_skim(FUNC, 7000, 10000, 300)

def test_skim():
    _help_test_skim_2(FUNC=skim)

def strpopL(num):
    s = str(num)
    if s[-1] == 'L':
        return s[:-1]
    return s

def intpopL(s):
    if type(s) is types.IntType:
        return long(s)
    if s[-1] == 'L':
        return int(s[:-1])
    else:
        return int(s)

def longpopL(s):
    if type(s) in (types.IntType, types.LongType,):
        return long(s)
    if s[-1] == 'L':
        return long(s[:-1])
    else:
        return long(s)

def intorlongpopL(s):
    if type(s) in (types.IntType, types.LongType,):
        try:
            return int(s)
        except OverflowError:
            return s
    if s[-1] == 'L':
        i = long(s[:-1])
    else:
        i = long(s)
    try:
        return int(i)
    except OverflowError:
        return i

def int_log_base_2(x):
    """
    Rounds down.

    @precondition `x' must be greater than or equal to 1.0.: x >= 1.0: "x: %s" % hr(x)
    """
    assert x >= 1.0, "precondition: `x' must be greater than or equal to 1.0." + " -- " + "x: %s" % hr(x)

    # Is it faster to use math.log and convert the result to base 2, or is it faster to do this?  Probably the former, but oh well...  --Zooko 2001-02-18
    y = 1
    res = -1
    while y <= x:
        res = res + 1
        y = y * 2

    return res

def int_log_base_10(x):
    """
    Rounds down.

    @precondition `x' must be greater than or equal to 1.0.: x >= 1.0: "x: %s" % hr(x)
    """
    assert x >= 1.0, "precondition: `x' must be greater than or equal to 1.0." + " -- " + "x: %s" % hr(x)

    # Is it faster to use len(str()), or is it faster to do this?  Probably the former, but oh well...  --Zooko 2001-02-18
    y = 1
    res = -1
    while y <= x:
        res = res + 1
        y = y * 10

    return res

class Timer:
    """
    A simple class to be used for timing of operations.
    """
    def __init__(self, start=None):
        self._result = None
        if start: self.start()
    def start(self):
        """starts the timer"""
        self._result = None
        self._start_time = time.time()
    def stop(self):
        """returns the time delta between now and when start was called"""
        self._stop_time = time.time()
        self._result = max(0.0000001, self._stop_time - self._start_time)
        return self._result
    def get(self):
        """returns the elapsed time between the most recent start and stop calls or the time elapsed if stop has not been called"""
        if self._result is not None:
            return self._result
        else:
            return max(0.0000001, time.time() - self._start_time)


class Counter:
    """
    A simple thread-safe counter.

    We could use operator overloading to create a class
    which acts like a number but is threadsafe, but this
    class requires explicit yet simple use, which seems
    preferable.
    """
    def __init__(self, value=0):
        self.v = value
        self.l = threading.Lock()
    def get(self):
        self.l.acquire()
        v = self.v
        self.l.release()
        return v
    def set(self, value):
        self.l.acquire()
        self.v = value
        self.l.release()
    def inc(self, amount=1):
        self.l.acquire()
        try:
            self.v = self.v + amount
        finally:
            self.l.release()
        return self.v
    def dec(self, amount=1):
        return self.inc(0 - amount)

class SimpleCounter:
    """
    A simple non-thread-safe counter.

    We could use operator overloading to create a class
    which acts like a number but is threadsafe, but this
    class requires explicit yet simple use, which seems
    preferable.
    """
    def __init__(self, value=0):
        self.v = value
    def get(self):
        v = self.v
        return v
    def set(self, value):
        self.v = value
    def inc(self, amount=1):
        self.v = self.v + amount
        return self.v
    def dec(self, amount=1):
        return self.inc(0 - amount)


class StackTree:
    """
    A dict with a stack representing the current path.
    This is handy for using the xml.sax style of parser
    to create a python dict.
    """
    def __init__(self):
        self.dict = {}
        self._path = []
    def get_current(self):
        current = self.dict
        for key in self._path:
            current = current[key]
        return current
    def push(self, name, value=None):
        if value == None:
            value = {}
        self.get_current()[name] = value
        self._path.append(name)
    def pop(self):
        return self._path.pop()

def common_substring_length(a, b, bitunits=true):
    """
    Returns the length of the common leading substring of a and b.
    If bitunits is true, this length is in bits, else it is
    in bytes.
    """
    count = 0
    maxlen = max(len(a), len(b))

    while count < maxlen and a[count] == b[count]:
        count = count + 1

    if bitunits:
        i = count
        count = count * 8
        if i < maxlen:
            # Does this craziness work?!  I think so.  -Neju 2001-02-18
            count = count + (7 - int_log_base_2(ord(a[i]) ^ ord(b[i])))

    return count

def zip(*args):
    """
    This is a naive implementation that does AFAICT the same thing that 
    the python 2.0 builtin `zip()' does.
    """
    res = []
    lenres = None

    for arg in args:
        if (lenres is None) or (len(arg) < lenres):
            lenres = len(arg)

    for i in range(lenres):
        newtup = []
        for arg in args:
            newtup.append(arg[i])
        res.append(tuple(newtup))

    return res

irange = lambda seq: zip(range(len(seq)), seq)

def doit(func):
    return func()

def coverageit(func):
    global tracedone
    tracedone.clear()
    debugprint("xxxxxxxxxxxxxxxxxxxx %s\n", args=(func,), v=0, vs="debug")
    coverage.the_coverage.start()
    # run the new command using the given trace
    try:
        result = apply(func)
        debugprint("yyyyyyyyyyyyyyyyyyyy %s\n", args=(func,), v=0, vs="debug")
    finally:
        coverage.the_coverage.stop()
        tmpfname = fileutil.mktemp(prefix=hr(func))

        debugprint("zzzzzzzzzzzzzzzzzzzz %s\n", args=(func,), v=0, vs="debug")

        # make a report, telling it where you want output
        res = coverage.the_coverage.analysis('/home/zooko/playground/evil-SF-unstable/common/MojoTransaction.py')
        print res
        tracedone.set()
    return result


def traceorcountit(func, dotrace, docount, countfuncs):
    global tracedone
    tracedone.clear()
    debugprint("xxxxxxxxxxxxxxxxxxxx %s, countfuncs: %s\n", args=(func, countfuncs,), v=0, vs="debug")
    t = trace.Trace(trace=dotrace, count=docount, countfuncs=countfuncs, infile="/tmp/trace", outfile="/tmp/trace", ignoredirs=(sys.prefix, sys.exec_prefix,))
    # run the new command using the given trace
    try:
        result = t.runfunc(func)
        debugprint("yyyyyyyyyyyyyyyyyyyy %s\n", args=(func,), v=0, vs="debug")
    finally:
        tmpfname = fileutil.mktemp(prefix=hr(func))

        debugprint("zzzzzzzzzzzzzzzzzzzz %s\n", args=(func,), v=0, vs="debug")

        # make a report, telling it where you want output
        t.results().write_results(show_missing=1)
        tracedone.set()
    return result

def traceit(func):
    return traceorcountit(func, dotrace=true, docount=false, countfuncs=false)

def countit(func):
    return traceorcountit(func, dotrace=false, docount=true, countfuncs=false)

def traceandcountit(func):
    return traceorcountit(func, dotrace=true, docount=true, countfuncs=false)

def countfuncsit(func):
    return traceorcountit(func, dotrace=false, docount=false, countfuncs=true)

def _dont_enable_if_you_want_speed_profit(func):
    result = None
    p = profile.Profile()
    try:
        debugprint("xxxxxxxxxxxxxxxxxxxx %s\n", args=(func,), v=0, vs="debug")
        result = p.runcall(func)
        debugprint("yyyyyyyyyyyyyyyyyyyy %s\n", args=(func,), v=0, vs="debug")
    finally:
        tmpfname = fileutil.mktemp(prefix=hr(func))

        debugprint("zzzzzzzzzzzzzzzzzzzz %s\n", args=(tmpfname,), v=0, vs="debug")

        p.dump_stats(tmpfname)
        p = None
        del p

        stats = pstats.Stats(tmpfname)
        stats.strip_dirs().sort_stats('time').print_stats()
    return result

def is_int(thing):
    return type(thing) in (types.IntType, types.LongType)

def is_number(thing):
    return type(thing) in (types.IntType, types.LongType, types.FloatType,)

def is_number_or_None(thing):
    return (thing is None) or (type(thing) in (types.IntType, types.LongType, types.FloatType,))

if confman.is_true_bool(('PROFILING',)):
    profit = _dont_enable_if_you_want_speed_profit
else:
    profit = doit
# profit = coverageit

global tracedone
tracedone = threading.Event()
tracedone.set() # if we actually do some tracing, we'll clear() it first then set() it afterwards.  That way you can wait() on this Event whether or not we do tracing.

# xor function:
xor = lambda a, b : (a and not b) or (not a and b)
xor.__doc__ = "The xor function is a logical exclusive-or."

def get_path_size(path):
    """
    If path is a non-directory, this returns the file's size.
    If path is a directory, this returns the sum of a recursive call on each path in that directory.
    If there's any OSError, return None
    """
    # XXX Keep an eye out for a standard library way of doing this.  os.path.walk seemed too restrictive.
    try:
        if os.path.isdir(path):
            return os.path.getsize(path) + reduce(lambda x, y: long(x)+y, filter(None, map(get_path_size, map(lambda p, base=path, os=os: os.path.join(base, p), os.listdir(path)))), 0)
        else:
            return os.path.getsize(path)
    except OSError:
        return None
        
def callback_wrapper(func, args=(), kwargs={}, defaultreturnval=None):
    """
    Use this with all callbacks to aid debugging.  When there is a TypeError it shows which function was being called
    (as opposed to just having a reference named something like "cb").

    @param defaultreturnval if `func' is None, then this will be returned;  You probably want `None'.
    """
##    if int(confman.dict['MAX_VERBOSITY']) >= 22:   # because traceback.extract_stack() is slow
##        debugprint("DEBUG: about to call wrapped method: %s(%s, %s) from %s\n", args=(func, args, kwargs, traceback.extract_stack()), v=22, vs="debug")
##        # really, really, egregiously verbose.  Use this if you basically want a log containing a substantial fraction of all function calls made during the course of the program.  --Zooko 2000-10-08 ### for faster operation, comment this line out.  --Zooko 2000-12-11 ### for faster operation, comment this line out.  --Zooko 2000-12-11

    if (not func):
        return defaultreturnval

#     try:
    try:
        return apply(func, args, kwargs)
    except TypeError, description:
        debugprint('got a TypeError, func was %s, args was %s, kwargs was %s\n' % (`func`, `args`, `kwargs`))
        raise
##    finally:
##        if int(confman.dict['MAX_VERBOSITY']) >= 23:   # because traceback.extract_stack() is slow
##            debugprint("DEBUG: done calling wrapped method: %s(%s, %s) from %s\n", args=(func, args, kwargs, traceback.extract_stack()), v=23, vs="debug")
##            # really, really, egregiously verbose.  Use this if you basically want a log containing a substantial fraction of all function calls made during the course of the program.  --Zooko 2000-10-08 ### for faster operation, comment this line out.  --Zooko 2000-12-11

def _cb_warper(icb=None):
    """
    This crazy function is for waiting for a callback and then examining the results.  (Just for
    testing.  Using this in production code is a no-no just like using "initiate_and_wait()".)

    Anyway, `_cb_warper()' takes a function.  It returns a tuple of `res', `reskw', `doneflag',
    and `_wcb'.  You pass `_wcb' as your callback, then call `doneflag.wait()'.  When your
    `wait()' call returns, you can look at `res' and `reskw' to see all of the values passed to
    the callback function.  Also your `icb' function, if it exists, got called before the
    `wait()' returned.

    @precondition `icb' is None or callable.: (not icb) or callable(icb): "icb: [%s]" % hr(icb)
    """
    assert (not icb) or callable(icb), "`icb' is None or callable." + " -- " + "icb: [%s]" % hr(icb)

    res=[]
    reskw={}
    doneflag = threading.Event()

    # this is a callable class, an instance of which will be used as the _wcb callback that we return
    class wrapped_callback:
        def __init__(self, icb, res, reskw, doneflag):
            self.icb = icb
            self.res = res
            self.reskw = reskw
            self.doneflag = doneflag
        def __call__(self, *args, **kwargs):
            resu = None
            if self.icb:
                resu = apply(self.icb, args, kwargs)
            self.res.extend(list(args))
            self.reskw.update(kwargs)
            self.doneflag.set()
            return resu

    return res, reskw, doneflag, wrapped_callback(icb, res, reskw, doneflag)

def cherrypick_best_from_list(lst, num):
    """
    Returns a list of length min(len(lst), num) items that have been
    picked randomly from the list with an exponential distribution,
    preferring to pick ones from the head of the list over the tail.

    SIDE EFFECT: Removes picked items from lst.
    """
    assert num >= 0
    cherry_list = []
    while lst and len(cherry_list) < num:
        idx = whrandom.randint(0, whrandom.randint(0, len(lst)-1))
        cherry_list.append(lst[idx])
        del lst[idx]
    return cherry_list

def rotatelist(lst):
    """
    Returns a new list that has been rotated a random amount
    """
    if len(lst) > 1:
        rotation = whrandom.randint(0, len(lst) - 1)
        return lst[rotation:] + lst[:rotation]
    else:
        return copy.copy(lst)


def shuffleList(list):
    """
    returns a new list with the items shuffled
    his isn't all that efficient (especially on space)
    """
    l = list[:] # make a copy so nothing unexpected happens to the caller
    shuffled = []
    length = len(l)
    for i in range(length):
        x = whrandom.randint(0, (length - 1) - i)
        shuffled.append(l[x])
        del l[x]
    return shuffled


def test_common_substring_length():
    s = '\000\000\000'
    d = '\000\000\001'
    assert common_substring_length(s, d) == 23, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

    s = '\000'
    d = '\001'
    assert common_substring_length(s, d) == 7, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

    s = '\000'
    d = '\000'
    assert common_substring_length(s, d) == 8, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

    s = '\000'
    d = '\000'
    assert common_substring_length(s, d, bitunits=false) == 1, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

    s = '\111'
    d = '\111'
    assert common_substring_length(s, d) == 8, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

    s = '\111' + chr(64)
    d = '\111' + chr(32)
    assert common_substring_length(s, d) == 9, "s: %s, d: %s, common_substring_length(s, d): %s" % (repr(s), repr(d), hr(common_substring_length(s, d)))

class DecompressError(StandardError, zlib.error): pass
class UnsafeDecompressError(DecompressError): pass # This means it would take more memory to decompress than we can spare.
class TooBigError(DecompressError): pass # This means it would exceed the maximum length that would be legal for the resulting uncompressed text.
class ZlibError(DecompressError): pass # internal error, probably due to the input not being proper compressedtext

def safe_zlib_decompress_to_retval(zbuf, maxlen=(65 * (2**20)), maxmem=(65 * (2**20))):
    """
    Decompress zbuf so that it decompresses to <= maxlen bytes or raise an exception.  If `zbuf' contains uncompressed data an exception will be raised.

    This function hopefully guards against zlib based memory allocation attacks.

    @param maxlen the resulting text must not be greater than this
    @param maxmem the execution of this function must not use more than this amount of memory in bytes;  The higher this number is (optimally 1032 * maxlen, or even greater), the faster this function can complete.  (Actually I don't fully understand the workings of zlib, so this function might use a *little* more than this memory, but not a lot more.)  (Also, this function will raise an exception if the amount of memory required even *approaches* `maxmem'.  Another reason to make it large.)  (Hence the default value which would seem to be exceedingly large until you realize that it means you can decompress 64 KB chunks of compressiontext at a bite.)

    @precondition `maxlen' must be a real maxlen, geez!: ((type(maxlen) == types.IntType) or (type(maxlen) == types.LongType)) and maxlen > 0: "maxlen: %s :: %s" % (hr(maxlen), hr(type(maxlen)))
    @precondition `maxmem' must be at least 1 MB.: maxmem >= 2 ** 20: "maxmem: %s" % hr(maxmem)
    """
    assert ((type(maxlen) == types.IntType) or (type(maxlen) == types.LongType)) and maxlen > 0, "precondition: `maxlen' must be a real maxlen, geez!" + " -- " + "maxlen: %s :: %s" % (hr(maxlen), hr(type(maxlen)))
    assert maxmem >= 2 ** 20, "precondition: `maxmem' must be at least 1 MB." + " -- " + "maxmem: %s" % hr(maxmem)

    lenzbuf = len(zbuf)
    offset = 0
    decomplen = 0
    availmem = maxmem - (76 * 2**10) # zlib can take around 76 KB RAM to do decompression

    decompstrlist = []

    decomp = zlib.decompressobj()
    while offset < lenzbuf:
        # How much compressedtext can we safely attempt to decompress now without going over `maxmem'?  zlib docs say that theoretical maximum for the zlib format would be 1032:1.
        lencompbite = availmem / 1032 # XXX TODO: The biggest compression ratio zlib can have for whole files is 1032:1.  Unfortunately I don't know if small chunks of compressiontext *within* a file can expand to more than that.  I'll assume not...  --Zooko 2001-05-12
        if lencompbite < 128:
            # If we can't safely attempt even a few bytes of compression text, let us give up.  This hopefully never happens.
            raise UnsafeDecompressError, "used up roughly `maxmem' memory. maxmem: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxmem), hr(len(zbuf)), hr(offset), hr(decomplen),)
        # I wish the following were a local function like this:
        # def proc_decomp_bite(tmpstr, lencompbite=0, decomplen=decomplen, maxlen=maxlen, availmem=availmem, decompstrlist=decompstrlist, offset=offset, zbuf=zbuf):
        # ...but until we can depend on Python 2.1 with lexical scoping, we can't update the integers like `offset'.  Oh well.  --Zooko 2001-05-12
        try:
            if (offset == 0) and (lencompbite >= lenzbuf):
                tmpstr = decomp.decompress(zbuf)
            else:
                tmpstr = decomp.decompress(zbuf[offset:offset+lencompbite])
        except zlib.error, le:
            raise ZlibError, (offset, lencompbite, decomplen, hr(le), )

        lentmpstr = len(tmpstr)
        decomplen = decomplen + lentmpstr
        if decomplen > maxlen:
            raise UnsafeDecompressError, "length of resulting data > `maxlen'. maxlen: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxlen), hr(len(zbuf)), hr(offset), hr(decomplen),)
        availmem = availmem - lentmpstr
        offset = offset + lencompbite
        decompstrlist.append(tmpstr)

    try:
        tmpstr = decomp.flush()
    except zlib.error, le:
        raise ZlibError, (offset, lencompbite, decomplen, le, )

    lentmpstr = len(tmpstr)
    decomplen = decomplen + lentmpstr
    if decomplen > maxlen:
        raise TooBigError, "length of resulting data > `maxlen'. maxlen: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxlen), hr(len(zbuf)), hr(offset), hr(decomplen),)
    availmem = availmem - lentmpstr
    offset = offset + lencompbite
    if lentmpstr > 0:
        decompstrlist.append(tmpstr)

    if len(decompstrlist) > 0:
        return string.join(decompstrlist, '')
    else:
        return decompstrlist[0]

def safe_zlib_decompress_to_file(zbuf, fileobj, maxlen=(65 * (2**20)), maxmem=(65 * (2**20))):
    """
    Decompress zbuf so that it decompresses to <= maxlen bytes or raise an exception.  If `zbuf' contains uncompressed data an exception will be raised.

    This function hopefully guards against zlib based memory allocation attacks.

    Note that this assumes that data written to `fileobj' continues to take up memory.

    @param maxlen the resulting text must not be greater than this
    @param maxmem the execution of this function must not use more than this amount of memory in bytes;  The higher this number is (optimally 1032 * maxlen, or even greater), the faster this function can complete.  (Actually I don't fully understand the workings of zlib, so this function might use a *little* more than this memory, but not a lot more.)  (Also, this function will raise an exception if the amount of memory required even *approaches* `maxmem'.  Another reason to make it large.)  (Hence the default value which would seem to be exceedingly large until you realize that it means you can decompress 64 KB chunks of compressiontext at a bite.)
    @param fileobj the decompressed text will be written to it

    @precondition `fileobj' must be an IO.: fileobj is not None
    @precondition `maxlen' must be a real maxlen, geez!: ((type(maxlen) == types.IntType) or (type(maxlen) == types.LongType)) and maxlen > 0: "maxlen: %s :: %s" % (hr(maxlen), hr(type(maxlen)))
    @precondition `maxmem' must be at least 1 MB.: maxmem >= 2 ** 20: "maxmem: %s" % hr(maxmem)
    """
    assert fileobj is not None, "precondition: `fileobj' must be an IO."
    assert ((type(maxlen) == types.IntType) or (type(maxlen) == types.LongType)) and maxlen > 0, "precondition: `maxlen' must be a real maxlen, geez!" + " -- " + "maxlen: %s :: %s" % (hr(maxlen), hr(type(maxlen)))
    assert maxmem >= 2 ** 20, "precondition: `maxmem' must be at least 1 MB." + " -- " + "maxmem: %s" % hr(maxmem)

    lenzbuf = len(zbuf)
    offset = 0
    decomplen = 0
    availmem = maxmem - (76 * 2**10) # zlib can take around 76 KB RAM to do decompression

    decomp = zlib.decompressobj()
    while offset < lenzbuf:
        # How much compressedtext can we safely attempt to decompress now without going over `maxmem'?  zlib docs say that theoretical maximum for the zlib format would be 1032:1.
        lencompbite = availmem / 1032 # XXX TODO: The biggest compression ratio zlib can have for whole files is 1032:1.  Unfortunately I don't know if small chunks of compressiontext *within* a file can expand to more than that.  I'll assume not...  --Zooko 2001-05-12
        if lencompbite < 128:
            # If we can't safely attempt even a few bytes of compression text, let us give up.  This hopefully never happens.
            raise UnsafeDecompressError, "used up roughly `maxmem' memory. maxmem: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxmem), hr(len(zbuf)), hr(offset), hr(decomplen),)
        # I wish the following were a local function like this:
        # def proc_decomp_bite(tmpstr, lencompbite=0, decomplen=decomplen, maxlen=maxlen, availmem=availmem, decompstrlist=decompstrlist, offset=offset, zbuf=zbuf):
        # ...but until we can use 2.1 lexical scoping we can't update the integers like `offset'.  Oh well.  --Zooko 2001-05-12
        try:
            if (offset == 0) and (lencompbite >= lenzbuf):
                tmpstr = decomp.decompress(zbuf)
            else:
                tmpstr = decomp.decompress(zbuf[offset:offset+lencompbite])
        except zlib.error, le:
            raise ZlibError, (offset, lencompbite, decomplen, le, )
        lentmpstr = len(tmpstr)
        decomplen = decomplen + lentmpstr
        if decomplen > maxlen:
            raise TooBigError, "length of resulting data > `maxlen'. maxlen: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxlen), hr(len(zbuf)), hr(offset), hr(decomplen),)
        availmem = availmem - lentmpstr
        offset = offset + lencompbite
        fileobj.write(tmpstr)

    try:
        tmpstr = decomp.flush()
    except zlib.error, le:
        raise ZlibError, (offset, lencompbite, decomplen, le, )
    lentmpstr = len(tmpstr)
    decomplen = decomplen + lentmpstr
    if decomplen > maxlen:
        raise UnsafeDecompressError, "length of resulting data > `maxlen'. maxlen: %s, len(zbuf): %s, offset: %s, decomplen: %s" % (hr(maxlen), hr(len(zbuf)), hr(offset), hr(decomplen),)
    availmem = availmem - lentmpstr
    offset = offset + lencompbite
    fileobj.write(tmpstr)

mojo_test_flag = 1

def update_weighted_sample(history, newvalue, historyweight=None,default_value=None):
    """
    @param history (mean, sigma, mean_squares,)
    @param newvalue new statistic to add to history with weighted deviation
    @param historyweight 0.0 = ignore history, 1.0 = ignore new sample
    @param default_value what to use when history param is None

    @returns updated history (mean, sigma, mean_squares,)
    """
    stat = history
    if stat is None:
        if default_value is None:
            stat = (float(newvalue), 0, float(newvalue)*float(newvalue))
        else:
            stat = (float(default_value), 0, float(default_value)*float(default_value))
    mean = float((historyweight * stat[0]) + ((1.0 - historyweight)*newvalue))
    mean_squares = float((historyweight * stat[2]) + ((1.0 - historyweight)*newvalue*newvalue))
    sigma_squared = mean_squares - mean*mean
    if sigma_squared > 0.0:
        sigma = math.sqrt(sigma_squared)
    else:
        # sigma = 0.0
        # ? I'm thinking we want to be a lot more lenient when we don't have enough samples yet.  --Zooko 2001-07-10
        sigma = math.sqrt(abs(mean))
    return (mean,sigma,mean_squares)
    

#### generic stuff
def run():
    # _help_testemall()
    # _help_benchemall()

    import RunTests
    RunTests.runTests(["mojoutil"])
   
#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

### standard modules
import new
import string
import threading
import traceback
import time
import random

### our modules
from MojoConstants import DEBUG_MODE
true=1
false=0
from confutils import confman
import debug
from wrappedmethod import wrappedmethod

def wrap_superclass_methods(thissuperclass, primaryclass):
    # For methods that belong to a superclass (and have not been over-ridden by the primary class) we'll generate a method in the primary class that overrides and locks.

    # If anyone calls a superclass method directly, i.e. `SpamClass.squish(self, howmuch)',
    # thus bypassing the primary class's override `squish(amount)' method, then they either
    # know what they are doing or they get what they deserve.

    # We ignore all methods whose names begin with "_".  They might be "magic" methods used by the interpreter, and in any case they are definitely private and should not be called from another object.  (So once again you know what you are doing or get what you deserve.)
    for (fname, func,) in thissuperclass.__dict__.items():
        if primaryclass.__dict__.has_key(fname):
            # nevermind, this has already been overridden.
            continue

        if (len(fname) >= 1) and (fname[0] == "_"):
            continue

        assert callable(func)
        wm = wrappedmethod(func)
        clas = thissuperclass

        wmum = new.instancemethod(wm, None, clas)

        # Put this wrapper callable obj where it will be used in the primary class, overriding the reference to the
        # superclass's method.
        primaryclass.__dict__[fname] = wmum

def wrap_primary_methods(primaryclass):
    # for methods that belong to the primary class:
    # rename each method by prepending "_Locker_real_", and then make a new method that does:
    # def foo():
    #     self.__enter()
    #     try:
    #         # ... the real method gets invoked here
    #     finally:
    #         self.__exit()

    # (For methods that belong to a superclass (and have not been over-ridden by the primary class) we'll generate a method in the primary class that overrides and locks.  See `wrap_superclass_methods()'.)

    # If anyone calls a superclass method directly, i.e. `SpamClass.squish(self, howmuch)',
    # thus bypassing the primary class's override `squish(amount)' method, then they either
    # know what they are doing or they get what they deserve.

    # We ignore all methods whose names begin with "_".  They might be "magic" methods used by the interpreter, and in any case they are definitely private and should not be called from another object.  (So once again you know what you are doing or get what you deserve.)

    for (fname, func,) in primaryclass.__dict__.items():
        if (len(fname) >= 1) and (fname[0] == "_"):
            continue

        assert not isinstance(func, wrappedmethod), "func: %s" % std.hr(func)

        assert callable(func)
        wm = wrappedmethod(func)
        clas = primaryclass

        wmum = new.instancemethod(wm, None, clas)

        # print " wrapping primary fname: %s, func: %s :: %s, wm: %s, :: %s, wmum: %s, :: %s" % (fname, func, type(func), wm, type(wm), wmum, type(wmum), )
        # Put this wrapper callable obj where it will be used, eliminating the reference to the
        # original method, which is now reachable only through the wrappedmethod.
        primaryclass.__dict__[fname] = wmum

def recursewrappem(classC, primaryclass):
    for classB in classC.__bases__:
        wrap_superclass_methods(classB, primaryclass)
        recursewrappem(classB, primaryclass)

def enable_locker(thisclass):
    wrap_primary_methods(thisclass)
    recursewrappem(thisclass, thisclass)

class Locker:
    """
    This ensures that objects are accessed by only one thread at a time.  It has five possible
    modes of operation, only one of which can be used per object, and which is chosen in the
    constructor.

    The five modes of operation are "blocking", "blocking-deadlock-detecting", "bombing",
    "sloppy-bombing" and "dummy".

    "blocking" means that the second thread that invokes a method of this object will be blocked
    until the first thread exits this object.  This mode can result in deadlocks, and is not
    recommended, although it is faster than "blocking-deadlock-detecting".

    "blocking-deadlock-detecting" mode is like "blocking" mode except that deadlock detection is
    also enabled;  An exception is raised if deadlock is detected, which will be very verbose if
    DEBUG_MODE is set.  This mode is recommended if you need to use the object in
    a multi-threaded way, but it is the slowest mode.

    "bombing" means that if more than one thread enters the object simultaneously, an exception
    will immediately be raised.  This mode is recommended if you intend to use the object in a
    single-threaded way, but bugs in your program are causing it to be used multi-threadedly,
    and you want to find those bugs.

    "sloppy-bombing" mode is like "bombing" mode, but it uses a fast and sloppy
    mechanism which can sometimes fail to detect multi-threading.

    "dummy" means don't do anything.  This is the fastest mode.
    """
    def __init__(self, mode="bombing", includelock=None, excludelock=()):
        """
        @param the class to whose methods lock will be added
        @param mode one of {"blocking", "blocking-deadlock-detecting", "bombing", "sloppy-bombing", "dummy"}
        @param includelock if `None', then include all methods of the object under threading
            protection; if not `None', then it is a sequence of methods -- include only
            those methods under threading protection
        @param excludelock a sequence of methods -- exclude those methods from threading
            protection (regardless of whether they were listed in `include' or not)

        @precondition `mode' must be one of {"blocking", "blocking-deadlock-detecting", "bombing", "sloppy-bombing", "dummy"}.: mode in ("blocking", "blocking-deadlock-detecting", "bombing", "sloppy-bombing", "dummy"): "mode: %s" % hr(mode)
        """
        assert mode in ("blocking", "blocking-deadlock-detecting", "bombing", "sloppy-bombing", "dummy"), "precondition: `mode' must be one of {\"blocking\", \"blocking-deadlock-detecting\", \"bombing\", \"sloppy-bombing\", \"dummy\"}." + " -- " + "mode: %s" % hr(mode)

        if mode == "blocking":
            self.__enter = self.__enter_blocking
            self.__exit = self.__exit_blocking
            self.__lock = threading.RLock()
        elif mode == "blocking-deadlock-detecting":
            self.__enter = self.__enter_blocking_deadlock_detecting
            self.__exit = self.__exit_blocking_deadlock_detecting
            self.__lock = threading.RLock() # deadlock detector
            self.__locklock = threading.Lock() # For protecting deadlock detector.
            if DEBUG_MODE:
                self.__lastthread = threading.currentThread()
                self.__lastthread2 = None
                self.__laststack = traceback.extract_stack()
                self.__laststack2 = None
        elif mode == "bombing":
            self.__enter = self.__enter_bombing
            self.__exit = self.__exit_bombing
            self.__lock = threading.RLock()
            if DEBUG_MODE:
                self.__lastthread = threading.currentThread()
                self.__lastthread2 = None
                self.__laststack = traceback.extract_stack()
                self.__laststack2 = None
        elif mode == "sloppy-bombing":
            self.__enter = self.__enter_sloppy_bombing
            self.__exit = self.__exit_sloppy_bombing
            self.__busy = false
            if DEBUG_MODE:
                self.__lastthread = threading.currentThread()
                self.__lastthread2 = None
                self.__laststack = traceback.extract_stack()
                self.__laststack2 = None
        elif mode == "dummy":
            return

    def __enter_bombing(self):
        res = self.__lock.acquire(blocking=false)
        if DEBUG_MODE:
            assert res, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread.  previous thread: %s, previous stack trace: %s, current thread: %s, previous^2 thread: %s, previous^2 stack trace: %s" % (`self.__lastthread`, `self.__laststack`, `threading.currentThread()`, `self.__lastthread2`, `self.__laststack2`)

            self.__laststack2 = self.__laststack
            self.__laststack = traceback.extract_stack()
            self.__lastthread2 = self.__lastthread
            self.__lastthread = threading.currentThread()
        else:
            assert res, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread."
        return

    def __exit_bombing(self):
        self.__lock.release()
        return

    def __enter_sloppy_bombing(self):
        if DEBUG_MODE:
            assert not self.__busy, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread.  previous thread: %s, previous stack trace: %s, current thread: %s, previous^2 thread: %s, previous^2 stack trace: %s" % (`self.__lastthread`, `self.__laststack`, `threading.currentThread()`, `self.__lastthread2`, `self.__laststack2`)

            self.__laststack2 = self.__laststack
            self.__laststack = traceback.extract_stack()
            self.__lastthread2 = self.__lastthread
            self.__lastthread = threading.currentThread()
        else:
            assert not self.__busy, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread."

        self.__busy = true

    def __exit_sloppy_bombing(self):
        if DEBUG_MODE:
            assert self.__busy, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread.  previous thread: %s, previous stack trace: %s, current thread: %s, previous^2 thread: %s, previous^2 stack trace: %s" % (`self.__lastthread`, `self.__laststack`, `threading.currentThread()`, `self.__lastthread2`, `self.__laststack2`)

            self.__laststack2 = self.__laststack
            self.__laststack = traceback.extract_stack()
            self.__lastthread2 = self.__lastthread
            self.__lastthread = threading.currentThread()
        else:
            assert self.__busy, "error -- This class is not multi-thread safe and it has been called simultaneously from more than one thread."
        self.__busy = false

    def __enter_blocking(self):
        self.__lock.acquire()
    def __exit_blocking(self):
        self.__lock.release()

    def __enter_blocking_deadlock_detecting(self):
        debug.stderr.write("Locker %s >-> ...  %s num=%s\n", args=(self, threading.currentThread().getName(), self.__lock._RLock__count), v=31, vs="debug")

        self.__locklock.acquire()
        try:
            satime = time.time()
            gotit = self.__lock.acquire(blocking=false)
            backoff = DEADLOCK_INITIAL_BACKOFF
            while ((time.time() - satime)<DEADLOCK_TOLERANCE) and (not gotit):
                debug.stderr.write("Locker %s --- retrying! ...  %s - num=%s\n", args=(self, threading.currentThread().getName(), self.__lock._RLock__count), v=5, vs="debug")

                time.sleep(backoff)
                backoff = (backoff * 2) + 0.001 # `+ 0.001' to avoid sticking at "0"
                gotit = self.__lock.acquire(blocking=false)
            if DEBUG_MODE:
                assert gotit, "error -- Deadlock.  previous thread: %s, previous stack trace: %s, previous^2 thread: %s, previous^2 stack trace: %s" % (`self.__lastthread`, `self.__laststack`, `self.__lastthread2`, `self.__laststack2`)

                self.__laststack2 = self.__laststack
                self.__laststack = traceback.extract_stack()
                self.__lastthread2 = self.__lastthread
                self.__lastthread = threading.currentThread()
            else:
                assert gotit, "error -- Deadlock."
        finally:
            self.__locklock.release()

    def __exit_blocking_deadlock_detecting(self):
        self.__lock.release()
        debug.stderr.write("Locker %s <-< ...  %s - num=%s\n", args=(self, threading.currentThread().getName(), self.__lock._RLock__count), v=31, vs="debug")


def test_simple():
    class Spam(Locker):
        def __init__(self):
            Locker.__init__(self)
            # print "after Locker: self.__dict__: %s\nself.__class__.__dict__: %s\n\n" % (self.__dict__, self.__class__.__dict__)
        def setx(self, newx):
            self.x = newx
        def printx(self, msg):
            print "msg: %s, self.x: %s\n" % (msg, self.x)
            pass

    enable_locker(Spam)

    s=Spam()

    # print "s.setx: %s :: %s, s.setx.im_func: %s" % (s.setx, type(s.setx), s.setx.im_func,)
    s.setx(3)
    # assert s._THINGIE == "hello!" # testing
    s.printx("hi there!")

def test_concurrent_blocking():
    class Spam2(Locker):
        def __init__(self):
            Locker.__init__(self, mode="blocking")
            self.x = 0
            self.y = 0
        def set(self, n):
            # print ">>>>> self: %s, n: %s, traceback: %s" % (self, n, traceback.extract_stack()[:-1],)
            self.x = n
            time.sleep(random.random() / 10.0) # yaawn...
            self.y = n
            # print "<<<<< self: %s, n: %s, traceback: %s" % (self, n, traceback.extract_stack()[:-1],)
        def assert_invariants(self):
            assert self.x == self.y, "self.x: %s, self.y: %s, self._Locker__lock: %s, self._Locker__lock._RLock__count: %s, self.set: %s, self.__dict__: %s, Spam2.__dict__: %s" % (self.x, self.y, self._Locker__lock, self._Locker__lock._RLock__count, self.set, self.__dict__, Spam2.__dict__,)
    # print "--- before locking: S.set: %s :: %s" % (Spam2.set, type(Spam2.set),)
    enable_locker(Spam2)
    # print "--- after locking: S.set: %s :: %s" % (Spam2.set, type(Spam2.set),)
    s = Spam2()
    # print "--- after instantiation: s.set: %s :: %s, s.set.im_func: %s" % (s.set, type(s.set), s.set.im_func,)
    fails=[]
    done1 = threading.Event()
    def set2(s=s, fails=fails, done1=done1):
        try:
            try:
                for i in xrange(2**8):
                    s.assert_invariants()
                    s.set(2)
                    s.assert_invariants()
                    time.sleep(random.random() / 1000.0) # yaawn...
            except:
                fails.append("oops")
                raise
        finally:
            done1.set()

    done2 = threading.Event()
    def set3(s=s, fails=fails, done2=done2):
        try:
            try:
                for i in xrange(2**8):
                    s.assert_invariants()
                    s.set(3)
                    s.assert_invariants()
                    time.sleep(random.random() / 1000.0) # yaawn...
            except:
                fails.append("oops")
                raise
        finally:
            done2.set()

    # Now, we're going to start two threads...
    threading.Thread(target=set2).start()
    threading.Thread(target=set3).start()
    done1.wait()
    done2.wait()
    assert len(fails) == 0

def test_concurrent_bombing():
    class Spam2(Locker):
        def __init__(self):
            Locker.__init__(self, mode="bombing")
            self.x = 0
            self.y = 0
        def set(self, n):
            self.x = n
            time.sleep(random.random() / 10.0) # yaawn...
            self.y = n
        def assert_invariants(self):
            assert self.x == self.y, "self.x: %s, self.y: %s, self._Locker__lock: %s, self._Locker__lock._RLock__count: %s" % (self.x, self.y, self._Locker__lock, self._Locker__lock._RLock__count)
    enable_locker(Spam2)
    s = Spam2()
    fails=[]
    done1 = threading.Event()
    def set2(s=s, fails=fails, done1=done1):
        try:
            try:
                for i in xrange(2**8):
                    s.set(2)
                    time.sleep(random.random() / 1000.0) # yaawn...
            except AssertionError:
                fails.append("oops")
                raise
        finally:
            done1.set()

    done2 = threading.Event()
    def set3(s=s, fails=fails, done2=done2):
        try:
            try:
                for i in xrange(2**8):
                    s.set(3)
                    time.sleep(random.random() / 1000.0) # yaawn...
            except AssertionError:
                fails.append("oops")
                raise
        finally:
            done2.set()

    # Now, we're going to start two threads...
    threading.Thread(target=set2).start()
    threading.Thread(target=set3).start()
    done1.wait()
    done2.wait()
    assert len(fails) > 0



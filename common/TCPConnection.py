#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard Python modules
import asyncore, socket, struct, sys, threading, time, traceback, types

# pyutil modules
import DoQ
from config import DEBUG_MODE
from debugprint import debugprint, debugstream
import humanreadable
import pyutilasync

# (old-)EGTP modules
from confutils import confman

# EGTP modules
import CommsError
import idlib

true = 1
false = None

# This is the maximum lowlevel EGTP message size; attempting to
# receive a message longer than this will cause the EGTP connection
# to be aborted.  Attempting to send a message longer than this
# will cause a fast fail.
MAXIMUM_MSG_SIZE = 4*(2**20) # 4 megabytes

class TCPConnection(asyncore.dispatcher):
    """
    Sends and receives buffers on TCP connections.  Prepends lengths for each message.
    """
    def __init__(self, inmsg_handler_func, key, close_handler_func=None, host=None, port=None, sock=None, commstratobj=None, throttlerin=None, throttlerout=None, cid_for_debugging=None):
        """
        @param key a key for identifying this connection;  (Hint: if you know the counterparty id use that, else use `idlib.make_new_random_id(thingtype='TCPConnection')')
        @param close_handler_func a function that gets called when the TCPConnection closes

        @precondition `key' must be a binary id.: idlib.is_binary_id(key): "key: %s :: %s" % (humanreadable.hr(key), humanreadable.hr(type(key)),)
        """
        assert idlib.is_binary_id(key), "precondition: `key' must be a binary id." + " -- " + "key: %s :: %s" % (humanreadable.hr(key), humanreadable.hr(type(key)),)

        # `_cid_for_debugging' is for debugging.
        self._cid_for_debugging = cid_for_debugging

        # `_key' is what we use to index this object in the TCPConnCache.  If we know the
        # counterparty id, then `_key' gets set to the counterparty id by the higher-level code
        # (by direct access to the `_key' member), else `_key' is set to a random unique id by
        # the higher-level code (in the constructor).
        self._key = key
        # XXX Hey -- could this be causing unexpected behaviour at some point if there were two different comm strats using the same key because they were with the same counterparty?  It shouldn't, because currently we supposedly always forget an old comm strat for a given counterparty before trying a new one.  (Although I don't know off the top of my head if this is accomplished with an if: condition or just by replacing the entry in the _conncache.)  But in the future we might keep multiple comm strats for one counterparty, so perhaps we shouldn't use the counterparty id as the key...  --Zooko 2001-05-07

        # for passing through to the fast fail handler
        self._commstratobj = commstratobj

        self._upward_inmsg_handler = inmsg_handler_func
        self._close_handler_func = close_handler_func

        # XXX multi-threading issues re: throttler
        self._throttlerread = throttlerin
        self._throttlerwrite = throttlerout

        self._readthrottled = false
        self._writethrottled = false

        self._inbufq = [] # this is a list of strings
        self._inbuflen = 0 # the current aggregate unconsumed bytes in inbufq (there can be leading byte in inbufq[0] which have already been consumed and are not counted by inbuflen)
        self._nextinmsglen = None # the length of the next incoming msg or `None' if unknown
        self._offset = 0 # the index of the beginning of the length-prefix of the next message (when there is no next message, `_offset' is 0)

        self._outmsgq = [] # contains (msg, fast_fail_handler_func) # for all subsequent outgoing messages that haven't begun sending yet
        self._outbuf = '' # the not-yet-sent part of the current outgoing message
        self._current_fast_fail_handler = None # the ffh for the current outgoing message

        if sock:
            self._everconnected = true  # we're already connected
        else:
            self._everconnected = false # `handle_connect()' sets this to true
        self._closing = false
        self._startedclosingonpyutilasync = false # to prevent multiple _finish_closing_on_pyutilasync calls, thus making `close()' idempotent
        self._closed = false # This gets set to `true' in `close()'.
        self._last_io_time = time.time() # the last time an IO event happened on this connection
        self._inmsgs = 0 # The total number of incoming messages that have come through this connection.
        self._nummsgs = 0 # The sum of outgoing and incoming messages that have come through this connection.
        self._outbytes = 0L # The total bytes ever sent over this connection.
        self._inbytes = 0L # The total bytes ever received over this connection.

        self._writable = false
        self._readable = true

        if self._throttlerread:
            self._throttlerread.register(self._throttle_read, self._unthrottle_read)
        if self._throttlerwrite:
            self._throttlerwrite.register(self._throttle_write, self._unthrottle_write)

        asyncore.dispatcher.__init__(self, sock=sock)
        if (not sock) and (host):
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.connect((host, port,))
            except socket.error, le:
                # This is not guaranteed to detect a failed connection, since connect() is a non-blocking call.  But if we _do_ get a socket error here then we have definitely failed.
                # debugprint("%s: couldn't connect to (%s, %s): %s\n", args=(self, host, port, le), v=1, vs="commstrats")
                self.close(reason=("socket.error on `connect()'", le,))
                raise CommsError.CannotSendError, ("socket.error on connect", le)

            DoQ.doq.add_task(self._fail_if_not_connected, delay=int(confman['TCP_CONNECT_TIMEOUT']))

        debugprint("%s created\n", args=(self,), v=5, vs="debug")

    def __repr__(self):
        try:
            if self._closed:
                state="closed"
            elif self._closing:
                state="closing"
            elif not self._everconnected:
                state="connecting"
            elif self._readthrottled:
                if self._writethrottled:
                    state="throttled in/out"
                else:
                    state="throttled in"
            elif self._writethrottled:
                state="throttled out"
            else:
                state="connected"

            try:
                pn = self.getpeername()
                return '<%s %s to %s at %s:%s, %x>' % (self.__class__.__name__, state, humanreadable.hr(self._cid_for_debugging), pn[0], pn[1], id(self))
            except:
                # `getpeername()' raises an exception sometimes, for example if the socket isn't connected yet.  That's a pretty silly interface, isn't it?  --Zooko 2001-06-17
                return '<%s %s to %s, %x>' % (self.__class__.__name__, state, humanreadable.hr(self._cid_for_debugging), id(self))
        except:
            debugprint("exception in TCPConnection.__repr__():\n")
            traceback.print_exc(file=debugstream)
            raise

    def _fail_if_not_connected(self):
        """
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."

        if self._everconnected:
            return
        # this causes it to be cleaned up and the fast fail handlers to be called appropriately
        self._fast_fail_reason = "connect() timeout"
        self.close(reason="not connected after timeout")

    def _set_closing(self):
        self._writable = false
        self._readable = false
        self._closing = true

    def _throttle_read(self):
        """
        No more data will be read in from the network until `unthrottle_read()' is called.

        @precondition This method must be called on the pyutilasync thread.: pyutilasync.selector.is_currently_asyncore_thread()
        """
        assert pyutilasync.selector.is_currently_asyncore_thread(), "precondition: This method must be called on the pyutilasync thread."

        self._readthrottled = 1 # `true'
        self._readable = 0 # `false'

    def _unthrottle_read(self):
        """
        @precondition This method must be called on the pyutilasync thread.: pyutilasync.selector.is_currently_asyncore_thread()
        """
        assert pyutilasync.selector.is_currently_asyncore_thread(), "precondition: This method must be called on the pyutilasync thread."

        self._readthrottled = None # `false'
        # Now if we are not closing then we are now ready to read.
        if not self._closing and not self._readable:
            self._readable = 1 # `true'

    def _throttle_write(self):
        """
        No more data will be written out to the network until `unthrottle_write()' is called.

        @precondition This method must be called on the pyutilasync thread.: pyutilasync.selector.is_currently_asyncore_thread()
        """
        assert pyutilasync.selector.is_currently_asyncore_thread(), "precondition: This method must be called on the pyutilasync thread."

        self._writethrottled = 1 # `true'
        self._writable = 0 # `false'

    def _unthrottle_write(self):
        """
        @precondition This method must be called on the pyutilasync thread.: pyutilasync.selector.is_currently_asyncore_thread()
        """
        assert pyutilasync.selector.is_currently_asyncore_thread(), "precondition: This method must be called on the pyutilasync thread."

        self._writethrottled = None # `false'
        # Now if we are not closing, and if there is data waiting to be sent, then we are ready to write.
        if not self._closing and (self._outbuf or self._outmsgq) and not self._writable:
            self._writable = 1 # `true'

    def send(self, msg, fast_fail_handler=None, pack=struct.pack):
        """
        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."

        if self._closing:
            debugprint("%s.send(%s): fast failed due to closing\n", args=(self, msg,), v=3, vs="debug")
            if fast_fail_handler:
                DoQ.doq.add_task(fast_fail_handler, kwargs={'failure_reason': "closing", 'bad_commstrat': self._commstratobj})
            return

        lenmsg = len(msg)
        if lenmsg > MAXIMUM_MSG_SIZE:
            if fast_fail_handler:
                DoQ.doq.add_task(fast_fail_handler, kwargs={'failure_reason': "message too long: %s" % humanreadable.hr(lenmsg)})
            return

        # TODO this is gross, it does a full data copy of the message just to prepend 4 bytes
        # (send should ideally accept buffer chains instead of a single string messages)
        # (this is not such a big deal as we're already spending many more cycles to encrypt every message)
        str = pack('>L', lenmsg) + msg

        self._outmsgq.append((str, fast_fail_handler,))
        # Now if we are not closing, and not write-throttled, then we are now ready to write.
        # (Note that it is possible for us to be closing now even though we tested just a few lines up because we are operating on the DoQ thread here and the asyncore thread can cause us to become closing.)
        if not self._closing and not self._writethrottled and not self._writable:
            self._writable = 1 # `true'
            pyutilasync.selector.wake_select()

        self._nummsgs = self._nummsgs + 1

    def is_idle(self, idletimeout=30):
        """
        @returns `true' if and only if there have been no I/O events have occured on this socket in >= idletimeout seconds or if it is closed
        """
        if self._closing:
            return true
        return (time.time() - self._last_io_time) >= idletimeout

    def is_talking(self):
        """
        @returns `true' if and only if there is a message actually half-sent or half-received
        """
        return (len(self._outbuf) > 0) or (self._inbuflen > 0) or (len(self._outmsgq) > 0)

    def is_busy(self, idletimeout):
        """
        @returns `true' if and only if (there is a message actually (half-sent or half-received)
            and not `is_idle(idletimeout)')
        """
        return self.is_talking() and not self.is_idle(idletimeout)

    #### methods below here are for internal use
    # The `handle_spam()' methods are the "bottom" interface, to be called by the asyncore thread.  There can be (one) thread touching the bottom interface and (one) thread touching the top interface at the same time.  Also `_chunkify()', which get called from `handle_spam()' methods.

    def close(self, reason=None):
        """
        The sequence of functions that get called to close a TCPConnection instance are:
         [*] close() -> [a] _finish_closing_on_pyutilasync -> [D] _finish_closing_on_doq
         `[*]' means that the function can be invoked from any thread, `[D]' means that the function must be
         invoked on the DoQ thread and `[a]' means that the function must be invoked on the pyutilasync thread.
         You should only ever call `close()', never any of the others.
         """
        debugprint("%s.close(reason: %s)\n", args=(self, reason,), v=5, vs="TCPConnection")

        self._set_closing()
        if pyutilasync.selector.is_currently_asyncore_thread():
            self._finish_closing_on_pyutilasync()
        else:
            assert DoQ.doq.is_currently_doq()
            pyutilasync.selector.add_task(self._finish_closing_on_pyutilasync)
            pyutilasync.selector.wake_select()

    def _finish_closing_on_pyutilasync(self):
        """
        It calls `asyncore.dispatcher.close(self)' to clean up the socket object.

        It then puts a task on the DoQ to do any cleaning-up that interacts with the DoQ world.
        (See `_finish_closing_on_doq'.)

        @precondition This method must be called on the pyutilasync thread.: pyutilasync.selector.is_currently_asyncore_thread()
        """
        assert pyutilasync.selector.is_currently_asyncore_thread(), "precondition: This method must be called on the pyutilasync thread."

        debugprint("%s._finish_closing_on_pyutilasync()\n", args=(self,), v=5, vs="TCPConnection")

        if self._startedclosingonpyutilasync:
            return
        self._startedclosingonpyutilasync = true

        # debugprint("%s.close(): about to asyncore.dispatcher.close()...\n", args=(self,))
        asyncore.dispatcher.close(self)
        # debugprint("%s.close(): done with asyncore.dispatcher.close()\n", args=(self,))

        DoQ.doq.add_task(self._finish_closing_on_doq)

    def _finish_closing_on_doq(self):
        """
        Does a fast-fail on any messages that were queued to be sent but haven't been sent yet.
        Unregisters from throttlers.

        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."

        assert self._closing
        assert self._startedclosingonpyutilasync

        debugprint("%s._finish_closing_on_doq()\n", args=(self,), v=5, vs="TCPConnection")

        if self._throttlerread:
            self._throttlerread.unregister(self._throttle_read, self._unthrottle_read)
        if self._throttlerwrite:
            self._throttlerwrite.unregister(self._throttle_write, self._unthrottle_write)

        if (not self._everconnected) or (self._outbytes == 0 and self._inbytes == 0):
            # debugprint("%s: connection refused: commstrat=%s, _everconnected=%s, _outbytes=%s, _inbytes=%s\n", args=(self, self._commstratobj, self._everconnected, self._outbytes, self._inbytes), v=6, vs="TCPConnection")
            connection_refused = 1
        else:
            connection_refused = None

        # Fail any partially sent message:
        # debugprint("%s.close(): about to Fail any partially sent message...\n", args=(self,))
        if (len(self._outbuf) > 0) and (self._current_fast_fail_handler):
            if hasattr(self, '_fast_fail_reason'):
                self._current_fast_fail_handler(failure_reason="TCPConnection: "+self._fast_fail_reason, bad_commstrat=self._commstratobj)
            elif connection_refused:
                self._current_fast_fail_handler(failure_reason="TCPConnection: connection refused", bad_commstrat=self._commstratobj)
            else:
                self._current_fast_fail_handler(failure_reason="TCPConnection: closed before message was sent")
        # debugprint("%s.close(): done with Fail any partially sent message\n", args=(self,))

        # debugprint("%s.close(): about to Fail any queued messages...\n", args=(self,))
        # Now fail any queued messages.
        while len(self._outmsgq) > 0:
            (str, ffh) = self._outmsgq.pop(0)
            if ffh:
                if connection_refused:
                    ffh(failure_reason="TCPConnection: connection refused", bad_commstrat=self._commstratobj)
                else:
                    ffh(failure_reason="TCPConnection: cannot send message")

        # send the event out to the TCPCommsHandler
        self._close_handler_func(self)

        # break the circular reference (hopefully our only remaining reference) from CommStrat.TCP object so that we disappear
        # (Note: all the rest of the stuff in this function shouldn't be necessary with good garbage collection but currently (Python >= 2.0 and at least
        # up to Python 2.2) the garbage collector won't collect garbage that has both a reference cycle and a __del__ method...)  --Zooko 2001-10-07
        if self._commstratobj and (self is self._commstratobj.asyncsock):
            self._commstratobj.asyncsock = None
            self._commstratobj = None

        # remove no longer needed function references
        self._upward_inmsg_handler = None
        self._current_fast_fail_handler = None
        self._close_handler_func = None

        # remove no longer needed object references
        self._commstratobj = None
        self._throttlerread = None
        self._throttlerwrite = None

        # empty our buffers
        self._outbuf = ''
        self._inbufq = []
        self._inbuflen = 0
        self._nextinmsglen = None

        self._closed = true

    def handle_write(self):
        if self._closing:
            return

        self._last_io_time = time.time()

        # load up the next message if any.
        if (len(self._outbuf) == 0) and (len(self._outmsgq) > 0):
            (str, ffh) = self._outmsgq.pop(0)
            self._current_fast_fail_handler = ffh
            self._outbuf = str

        if len(self._outbuf) > 0:
            try:
                num_sent = asyncore.dispatcher.send(self, self._outbuf)
                # debugprint("%s.handle_write(): sent [%s] bytes\n", args=(self, num_sent), v=9, vs="commstrats") ### for faster operation, comment this line out.  --Zooko 2000-12-11
            except socket.error, le:
                # debugprint("%s.handle_write(): got exception: %s\n", args=(self, le,), v=6, vs="commstrats")
                self.close(reason=("socket.error on `send()'", le,))
                return

            self._outbytes = self._outbytes + num_sent
            self._outbuf = self._outbuf[num_sent:]
            if len(self._outbuf) == 0:
                self._current_fast_fail_handler = None   # remove the no longer needed function reference!
                # Now if there are no more messages waiting to be sent, then we are no longer ready to write.
                if not self._outmsgq:
                    self._writable = 0 # `false'
            if self._throttlerwrite:
                self._throttlerwrite.used(num_sent) # notify throttler we just used up some bandwidth

    def writable(self):
        return self._writable

    def readable(self):
        return self._readable

    def _chunkify(self, nextstream, unpack=struct.unpack):
        """
        @precondition `self._upward_inmsg_handler' must be callable.: callable(self._upward_inmsg_handler): "self._upward_inmsg_handler: %s :: %s" % (humanreadable.hr(self._upward_inmsg_handler), humanreadable.hr(type(self._upward_inmsg_handler)),)
        """
        assert callable(self._upward_inmsg_handler), "precondition: `self._upward_inmsg_handler' must be callable." + " -- " + "self._upward_inmsg_handler: %s :: %s" % (humanreadable.hr(self._upward_inmsg_handler), humanreadable.hr(type(self._upward_inmsg_handler)),)

        assert (self._inbuflen == 0) or (len(self._inbufq) > 0), "self._inbuflen: %s, self._inbufq: %s" % (humanreadable.hr(self._inbuflen), humanreadable.hr(self._inbufq),)

        lennextstream = len(nextstream)
        if lennextstream == 0:
            debugprint("warning %s._chunkify(%s): length 0\n", args=(self, nextstream,), v=0, vs="debug")
            return
        
        # Using local variables is faster inside the coming loop, but on the other hand there is a cost to creating the local variables.  I think it's probably still a win though, as these can get accessed multiple times during a single call to `_chunkify()'.  --Zooko 2001-09-21
        nextinmsglen = self._nextinmsglen
        inbufq = self._inbufq
        inbuflen = self._inbuflen
        offset = self._offset

        inbuflen = inbuflen + lennextstream
        inbufq.append(nextstream)
        # debugprint("%s._chunkify() called, nextinmsglen: %s, inbuflen: %s, offset: %s, inbufq: %s\n", args=(self, nextinmsglen, inbuflen, offset, inbufq,), v=0, vs="debug")
        assert (inbuflen == 0) or (len(inbufq) > 0), "inbuflen: %s, inbufq: %s" % (humanreadable.hr(inbuflen), humanreadable.hr(inbufq),)

        if (nextinmsglen is None) and (inbuflen >= 4):
            # collect the four bytes.  (Note that 99% of the time we will execute the while loop body zero times and the remaining 1% of the time we will execute it one time, unless there is something REALLY funny going on -- that is, unless `_chunkify()' was called with `nextstream' was of size 1.)
            assert len(inbufq) > 0, "inbufq: %s" % humanreadable.hr(inbufq)
            while len(inbufq[0]) < (offset + 4):
                assert len(inbufq) > 1, "inbufq: %s" % humanreadable.hr(inbufq)
                inbufq[0] = inbufq[0] + inbufq[1]
                del inbufq[1]

            assert len(inbufq[0]) >= (offset + 4), "inbufq: %s, offset: %s" % humanreadable.hr(inbufq, offset,)

            nextinmsglen = unpack('>L', inbufq[0][offset:(offset + 4)])[0]
            assert type(nextinmsglen) is types.LongType
            # debugprint("%s._chunkify(): nextinmsglen: %s\n", args=(self, nextinmsglen,), v=6, vs="debug")
            if nextinmsglen > MAXIMUM_MSG_SIZE:
                # Too big.
                debugprint("%s._chunkify(): killing due to overlarge msg size. nextinmsglen: %s, inbuflen:%s, offset: %s, inbufq: %s\n", args=(self, nextinmsglen, inbuflen, offset, inbufq,), v=0, vs="debug")
                self.close(reason=("overlarge msg size", nextinmsglen,))
                return
            nextinmsglen = int(nextinmsglen)
            if DEBUG_MODE and nextinmsglen > (260 * 2**10):
                debugprint("%s._chunkify(): suspiciously large msg size. nextinmsglen: %s, inbuflen:%s, offset: %s, inbufq: %s\n", args=(self, nextinmsglen, inbuflen, offset, inbufq,), v=0, vs="debug")

        # Now this is the loop to extract and upsend each message.  Note that we replicate the "extract next msg len" code from above at the end of this loop.  This is the common idiom of "compute a value; while it is big enough: do some stuff; compute the value again"
        while (nextinmsglen is not None) and (inbuflen >= (nextinmsglen + 4)):
            # debugprint("%s._chunkify(), in loop offset: %s, inbufq: %s\n", args=(self, offset, inbufq,), v=0, vs="debug")
            assert (inbuflen == 0) or (len(inbufq) > 0), "inbuflen: %s, inbufq: %s" % (humanreadable.hr(inbuflen), humanreadable.hr(inbufq),)
            # debugprint("%s._chunkify(): collecting next message of length: %s\n", args=(self, nextinmsglen,), v=6, vs="debug")
            leninbufq0 = len(inbufq[0])
            nextchunki = nextinmsglen+offset+4
            assert leninbufq0 >= (offset + 4)
            if leninbufq0 > nextchunki:
                msg = inbufq[0][(offset + 4):(nextinmsglen+offset+4)]
                # Set offset to point to the beginning of the unconsumed part:
                offset = nextinmsglen+offset+4
            elif leninbufq0 == nextchunki:
                msg = inbufq[0][(offset + 4):]
                offset = 0
                del inbufq[0]
            else: # leninbufq0 < nextchunki
                msg = inbufq[0][(offset + 4):]
                remain = nextinmsglen - len(msg)
                i = 1
                offset = 0
                while remain > 0:
                    leninbufqi = len(inbufq[i])
                    if leninbufqi > remain:
                        # Append the part of the buf that is the trailing part of this msg.
                        msg = msg + inbufq[i][:remain]
                        # Set offset to point to the beginning of the unconsumed part:
                        offset = remain
                        remain = 0
                        del inbufq[:i]
                    elif leninbufqi == remain:
                        msg = msg + inbufq[i]
                        offset = 0
                        remain = 0
                        del inbufq[:i+1]
                    else: # leninbufqi < remain
                        msg = msg + inbufq[i]
                        remain = remain - leninbufqi
                    i = i + 1
            inbuflen = inbuflen - (nextinmsglen + 4)
            assert (inbuflen == 0) or (len(inbufq) > 0), "inbuflen: %s, inbufq: %s" % (humanreadable.hr(inbuflen), humanreadable.hr(inbufq),)

            self._inmsgs = self._inmsgs + 1
            self._nummsgs = self._nummsgs + 1

            # debugprint("%s._chunkify(): got message of length: %s, msg: %s\n", args=(self, nextinmsglen, msg,), v=6, vs="debug")
            DoQ.doq.add_task(self._upward_inmsg_handler, args=(self, msg))

            # Okay we're done with that message!  Now recompute nextinmsglen.
            if inbuflen < 4:
                nextinmsglen = None
            else:
                # collect the four bytes.  (Note that 99% of the time we will execute the while loop body zero times and the remaining 1% of the time we will execute it one time, unless there is something REALLY funny going on -- that is, unless `_chunkify()' was called with `nextstream' was of size 1.)
                assert len(inbufq) > 0, "inbufq: %s" % humanreadable.hr(inbufq)
                while len(inbufq[0]) < (offset + 4):
                    assert len(inbufq) > 1, "inbufq: %s" % humanreadable.hr(inbufq)
                    inbufq[0] = inbufq[0] + inbufq[1]
                    del inbufq[1]

                assert len(inbufq[0]) >= (offset + 4), "inbufq: %s, offset: %s" % humanreadable.hr(inbufq, offset,)

                nextinmsglen = unpack('>L', inbufq[0][offset:(offset + 4)])[0]
                assert type(nextinmsglen) is types.LongType
                # debugprint("%s._chunkify(): nextinmsglen: %s\n", args=(self, nextinmsglen,), v=6, vs="debug")
                if nextinmsglen > MAXIMUM_MSG_SIZE:
                    # Too big.
                    debugprint("%s._chunkify(): killing due to overlarge msg size. nextinmsglen: %s, inbuflen:%s, offset: %s, inbufq: %s\n", args=(self, nextinmsglen, inbuflen, offset, inbufq,), v=0, vs="debug")
                    self.close(reason=("overlarge msg size", nextinmsglen,))
                    return
                nextinmsglen = int(nextinmsglen)
                if DEBUG_MODE and nextinmsglen > (260 * 2**10):
                    debugprint("%s._chunkify(): suspiciously large msg size. nextinmsglen: %s, inbuflen:%s, offset: %s, inbufq: %s\n", args=(self, nextinmsglen, inbuflen, offset, inbufq,), v=0, vs="debug")

        self._nextinmsglen = nextinmsglen
        self._inbufq = inbufq
        self._inbuflen = inbuflen
        self._offset = offset
        assert (self._inbuflen == 0) or (len(self._inbufq) > 0), "self._inbuflen: %s, self._inbufq: %s" % (humanreadable.hr(self._inbuflen), humanreadable.hr(self._inbufq),)

    def handle_read(self):
        if self._closing:
            return

        self._last_io_time = time.time()
        try:
            data = self.recv(65536)
            # debugprint("%s.handle_read(): received [%s] bytes\n", args=(self, len(data)), v=9, vs="commstrats") ### for faster operation, comment this line out.  --Zooko 2000-12-11
        except socket.error, le:
            # This is the socket's way of telling us that we are _closed_.
            # debugprint("%s: closed socket detected. le:%s\n", args=(self, le), v=6, vs="commstrats")
            self.close(reason=("socket.error on `recv()'", le,))
            return
        except MemoryError, le:
            debugprint("memory error in TCPConnection.read()\n")
            self.close() # the best thing to do is close the connection, that frees some memory, makes our internal state consistent, and signals our peers that we're not so good right now
            return

        if len(data) == 0:
            # This is the socket's way of telling us that we are _closed_.
            # debugprint("%s: closed socket detected.  (read of length 0)\n", args=(self,), v=6, vs="commstrats")
            self.close()
            return
        self._inbytes = self._inbytes + len(data)
        if self._throttlerread:
            self._throttlerread.used(len(data)) # notify throttler we just used up some bandwidth
        self._chunkify(data)

    def handle_accept(self) :
        debugprint("%s.handle_accept() checking to see if this gets called...\n", args=(self,), v=0, vs="debug")

    def handle_connect(self):
        self._last_io_time = time.time()
        self._everconnected = true
        # debugprint("%s.handle_connect()\n", args=(self,), v=6, vs="commstrats")

    def handle_close(self):
        # debugprint("%s.handle_close()\n", args=(self,), v=6, vs="commstrats")
        self.close()

    def log(self, message):
        # for faster operation, comment this whole method out and replace it with "def log(): return".  --Zooko 2000-12-11
        return
##        if message[-1:] == "\n":
##            debugprint("%s: asyncore log: %s", args=(self, message,), v=15, vs="commstrats")
##        else:
##            debugprint("%s: asyncore log: %s\n", args=(self, message,), v=15, vs="commstrats")

def test_close_on_bad_length(pack=struct.pack):
    outputholder = [None]
    def inmsg(tcpc, msg, outputholder=outputholder):
        outputholder[0] = msg

    t = TCPConnection(inmsg, idlib.new_random_uniq())
    msg = "hellbo"
    str = pack('>L', 2**30) + msg
    t._chunkify(str)
    DoQ.doq.flush()
    assert t._closing

def test_chunkify():
    outputholder = [None]
    def inmsg(tcpc, msg, outputholder=outputholder):
        outputholder[0] = msg

    t = TCPConnection(inmsg, idlib.new_random_uniq())

    def help_test(msgs, iseq, t=t, outputholder=outputholder, pack=struct.pack):
        str = ''
        for msg in msgs:
            str = str + pack('>L', len(msg)) + msg
        oldi = 0
        for i in iseq:
            t._chunkify(str[oldi:i])
            oldi = i
            DoQ.doq.flush() # the upward inmsg push happens on the DoQ.
        assert outputholder[0] == msg

    msgs = ["goodbyte",]

    help_test(msgs, range(1, len(msgs[0])+5))
    help_test(msgs, range(4, len(msgs[0])+5))
    help_test(msgs, range(5, len(msgs[0])+5))

    msgs = ["hellbo", "goodbyte",]
    help_test(msgs, range(1, 23))
    help_test(msgs, (1, 5, 9, 23,))
    help_test(msgs, (4, 9, 23,))
    help_test(msgs, (11, 12, 23,))

    msgs = ["hellbo", "goodbyte", "wheedle, wordling!",]
    help_test(msgs, (10, 20, 30, 40, 50,))
    help_test(msgs, (5, 10, 20, 30, 40, 50,))
    help_test(msgs, (15, 20, 30, 40, 50,))
    help_test(msgs, (15, 17, 23, 40, 50,))


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# A module containing user-configuration utilities, debug stuff and
# many other functions.  This file is -way- too big but was lumped all
# into one to prevent circular chicken & egg import problems with the
# way it was before.  Don't import this directly if possible, import
# the sub modules that import things from this (debug, confutils,
# mojoutil, idlib, etc..)
#
__cvsid = '$Id: mojostd.py,v 1.2 2002/01/29 22:40:31 zooko Exp $'


### Imports:
# Standard Modules:
import UserDict
import copy
import binascii
import exceptions
import glob
import operator
import os
from pprint import pprint
import Queue
import cStringIO
import sha
import stat
import string
import sys
import threading
import time
import traceback
import types
import re
import whrandom


### Our modules:
import HashRandom
from MojoConstants import true, false
import MojoConstants
from VersionNumber import VersionNumber
import dictutil
import fileutil
from humanreadable import hr
import mencode
import modval
import mojosixbit
import randsource
import timeutil
import time

def iso_utc_time(t=None):
    """
    Return an ISO-8601 formatted time in UTC.  If parameter t is given, it should be the local
    machine time since the epoch in seconds as returned by time.time().  The default is to return a
    string representing "now".

    Note that this is the system's guess about the current UTC, and it cannot be
    trusted to be accurate.  In particular, it can probably be manipulated by an
    attacker and in addition it can jump forward and backward arbitrarily between
    two successive invocations.  It should be used only for human-readable logs,
    not computed upon.
    """
    if not t:
        t = time.gmtime(time.time())
    else:
        t = time.gmtime(t)
    return time.strftime('%Y-%m-%d_%H:%M:%S', t)


def test_iso8601_utc_time(timer=timeutil.timer):
    ts1 = iso_utc_time(timer.time() - 20)
    ts2 = iso_utc_time()
    assert ts1 < ts2, "failed: %s < %s" % (ts1, ts2)
    ts3 = iso_utc_time(timer.time() + 20)
    assert ts2 < ts3, "failed: %s < %s" % (ts2, ts3)


def iso_utc_time_to_localseconds(isotime, _conversion_re=re.compile(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})")):
    """The inverse of iso_utc_time()"""
    m = _conversion_re.match(isotime)
    if not m:
        raise ValueError, (isotime, "not a complete ISO8601 timestamp")
    year, month, day = int(m.group('year')), int(m.group('month')), int(m.group('day'))
    hour, minute, second = int(m.group('hour')), int(m.group('minute')), int(m.group('second'))
    utcseconds = time.mktime( (year, month, day, hour, minute, second, 0, 1, 0) )
    localseconds = utcseconds - time.timezone
    return localseconds

def test_iso_utc_time_to_localseconds(timer=timeutil.timer):
    # test three times of the year so that a DST problem would hopefully be triggered
    t1 = int(time.time() - 365*3600/3)
    iso_utc_t1 = iso_utc_time(t1)
    t1_2 = iso_utc_time_to_localseconds(iso_utc_t1)
    assert t1 == t1_2, (t1, t1_2)
    t1 = int(timer.time() - (365*3600*2/3))
    iso_utc_t1 = iso_utc_time(t1)
    t1_2 = iso_utc_time_to_localseconds(iso_utc_t1)
    assert t1 == t1_2, (t1, t1_2)
    t1 = int(timer.time())
    iso_utc_t1 = iso_utc_time(t1)
    t1_2 = iso_utc_time_to_localseconds(iso_utc_t1)
    assert t1 == t1_2, (t1, t1_2)

####################### determine where the broker files are stored #######################

# HOME_DIR is a "home directory" such as /home/johndoe on unix systems.  It is
# dictated here for flexability's sake.
if os.environ.has_key('HOME'):
    HOME_DIR = '${HOME}'
else:
    # The environment variable wasn't set, so use this hardcoded constant:
    if sys.platform in ("linux", "bsd"):
        HOME_DIR = os.path.normpath("/var/tmp/mojonation")
    else:
        HOME_DIR = os.path.normpath(r"\My Documents")

if os.environ.has_key('EVILCONFDIR'):
    BROKER_DIR = os.path.normpath(
            os.path.join("${EVILCONFDIR}", "broker")
        )
else:
    # The environment variable wasn't set, so use this hardcoded constant:
    BROKER_DIR = os.path.normpath(
            os.path.join(HOME_DIR, ".mojonation/broker")
        )
    # !X! Note: Make sure all platforms can have directory names beginning with ".".

########################################## HERE IS THE debug.py PART OF mojostd.py

### Constants:
COLORCODE_RED    = '\033[01;31m%s\033[00m'
COLORCODE_GREEN  = '\033[01;32m%s\033[00m'
COLORCODE_YELLOW = '\033[01;33m%s\033[00m'
COLORCODE_BLUE   = '\033[01;34m%s\033[00m'
COLORCODE_NONE   = '%s'

### Functions:
def hilight(string, colorcode=COLORCODE_NONE):
    """
    @precondition string must be of the right type.: type(string) == types.StringType

    @returns the string surrounded by Linux compatible color codes for blue.
    """
    assert type(string) == types.StringType, "string must be of the right type."

    return colorcode % string

### Classes:
class DebugStream:
    '''Acts like a file, such as sys.stderr; Writes debug info to logstream.'''
    def __init__(self, logstream = sys.stderr, logfile=None, filters=[], log_vs=[]):
        """
        logstream and logfile are both files.  (-I don't see a distinction! --Neju 2001-02-06)

        filters is a list of filter functions.  These take a single string argument and return a single string
            argument.  DebugStream formats calls to its write method, and then passes the result to
            the first filter (if any).  The return from that filter is applied to the next, and so on.
            The final return value (or the original string if there are no filters) is written to
            logstream and logfile.

        Note: The filter design could eliminate the need for the other two files altogether!
        Furthermore the filters can be modified at runtime.  An example of this being used
        in real life is for the BrokerTk MojoMod, which installs a filter to copy all DebugStream
        to a GUI widget before it is sent out to a file.
        """
        self.filters = filters[:] # Copy it (don't modify the default!)
        self._writeQ = Queue.Queue(0) # holds tuples of (output, v, vs, args)
    
        if logfile:
            # Supposedly `touch()' should have created all directories that appear in the PATH key in confutils.
            # But that's not happening in practice and anyway it sometimes causes problems by trying to create
            # directories that aren't needed (for example, when you're just trying to do some util like extracting
            # file metadata instead of trying to start an actual live broker).
            # So I'm just gonna make sure the path exists here, which is where I am getting runtime errors
            # due to its non-existence.  --Zooko 2001-09-29
            fileutil.make_dirs(os.path.dirname(logfile))
            self._logfile = open(logfile, "wt")
            #print "log being written to", logfile
        else:
            self._logfile = None
        self.logstream = logstream
        self.lastchar = '\n'
        if len(log_vs):
            self.log_vs = {}
            for i in log_vs:
                self.log_vs[i] = 1
        else:
            self.log_vs = None

        return

    def shutdown(self):
        if self._logfile:
            self._logfile.close()

    def __getattr__(self, attribute):
        '''Pretend to be self.logstream.'''
        return eval("self.logstream.%s" % attribute)

    def close(self):
        if self._logfile:
            self._logfile.close()
            self._logfile = None
    
    def get_log_vs(self):
        if self.log_vs:
            return self.log_vs.keys()
        else:
            return None
    def reset_log_vs(self, new_vs):
        if len(new_vs):
            self.log_vs = {}
            for i in new_vs:
                self.log_vs[i] = 1
        else:
            self.log_vs = None
            
    def get_name(self):
        if self._logfile:
            return self._logfile.name
        else:
            return ''

    def rotate_logfile(self, newfilename):
        if not self._logfile:
            return
        oldlogfile = self._logfile
        self.write("Rotating mojolog: Closing %s, Opening %s\n" % (self.get_name(), newfilename), vs='mojolog')
        newlogfile = open(newfilename, "wt")
        self._logfile = newlogfile
        self.write("This log file is continuation of: %s\n" % (oldlogfile.name,), vs='mojolog')
        oldlogfile.close()

    def _filter(self, output):
        for filter in self.filters:
            try:
                output = filter(output)
            except:
                # Bad filter!
                output = output + '\nACK!  DebugStream filter %s raised exception:\n' % `filter`
                f = cStringIO.StringIO()
                traceback.print_exc(file=f)
                output = output + f.getvalue()
                del f
        return output
    
    def writer_loop(self):
        while 1:
            pass #XXXX Amber left off here.   --Zooko 2000-10-16

    def write(self, output, v=0, vs="", args=()):
        """
        Writes output to stderr.  Pretty-prints non-strings.  Filters specific stuff out.

        @param v the verbosity level of this message;  If it is less than or equal to
            MAX_VERBOSITY, then the string will be written.
        @param vs the purpose of this message;  This string is included in the output.  In the
            future we may use this string to determine whether to print the message out to the
            user, log it to a log file, drop it on the floor, etc.  Suggested values: "error",
            "debug", "user", or specific things that you might want to get diagnostics on e.g.
            "commstrats", "comm hints", "accounting".
        @param args if a tuple is specified output will be run through the % operator with args:
            "output = output % hr(args)"  The advantage of this is that the possibly expensive %
            and`hr()' functions won't be executed unless the message is being printed.
        """
        # Note:  This interface overloads the standard file write interface.  Make sure this is always a compatible
        # superset of the standard file interface, so we can pass this around to third-party or standard modules
        # which use files!
        if type(v) != types.IntType:
            self._internal_write('ERROR: the next debug message called write() with a non-integer v: %s\n', args=(v,), v=0)
            v = 0
        if v:
            if v > int(confman.get("MAX_VERBOSITY", "1")):
                return # Don't write this, because it is too verbose for us.

        if self.log_vs and vs:
            if not self.log_vs.has_key(vs):
                return
        if type(output) == types.StringType:
            if self.lastchar == '\n':
                timestr = iso_utc_time()
                if not vs:
                    vs=""
                #outline = "%s (%s): [%s]: " % (threading.currentThread().getName(), vs, timestr)
                outline = "%s (%s) " % (timestr, vs)
            else:
                outline = ""

            if args:
                try:
                    output = output % tuple(map(hr, args))
                except TypeError, e:
                    output = "ERROR: output string '%s' contained invalid %% expansion (note that we only do %%s around here), error: %s, args: %s\n" % (`output`, e, `args`)

            outline = outline + re.sub(r"\n", r"\n: ", output[:-1]) + output[-1:]

            outline = self._filter(outline)

            if self._logfile:
                self._logfile.write(outline)
                self._logfile.flush()

            if self.logstream:
                self.logstream.write(outline)
                self.logstream.flush()

            self.lastchar = output[-1]

        elif type(output) == types.DictType:
            self.dict_id("", output)
        else:
            pprint(output, self)

    def dict_id(self, key, dict, depth=0):
        indent = "    " * depth
        self.write("%s%s: <%d>\n" % (indent, key, id(dict)))
        for key in dict.keys():
            if type(dict[key]) == types.DictType:
                self.dict_id(key, dict[key], depth + 1)
            else:
                self.write("%s%s: %s\n" % (indent + "    ", key, dict[key]))
        return

def generate_mojolog_filename():
    # remove :s from time, they're not allowed in filenames on dos.
    logdir = os.path.expandvars(BROKER_DIR)
    pre= os.path.join(logdir, "mojolog-" + string.replace(iso_utc_time(), ':', '_'))
    if sys.platform == "darwin1":
    	post = ".log"
    else:
    	post=".txt"
    tempfile = pre + post
    return tempfile

def cleanup_old_mojologs(maxage_in_hours, currentfilename, timer=timeutil.timer):
    required_mtime = timer.time() - (maxage_in_hours * 60 * 60)
    logdir = os.path.expandvars(BROKER_DIR)

    mojologs = glob.glob(os.path.join(logdir, "mojolog-") + '*')
    for logfile in mojologs:
        if logfile == currentfilename:
            continue
        if os.path.isfile(logfile) and os.stat(logfile)[stat.ST_MTIME] < required_mtime:
            try:
                os.unlink(logfile)
                mojolog.write('Removed old mojolog %s\n', args=(logfile,), vs='mojolog')
            except:
                mojolog.write('Unable to remove old mojolog %s\n', args=(logfile,), vs='mojolog')

# Now instantiate a DebugStream wrapper to be our mojolog:
if ('--no-log-file' in sys.argv):
    __logfile = None
else:
    for arg in sys.argv:
        if arg[:len('--log-file=')] == '--log-file=':
            __logfile = arg[len('--log-file='):]
            break
    else:
        # write directly to a log file by default on windows
        __logfile = generate_mojolog_filename()

if os.environ.has_key('__RUN_MOJO_BROKER_SILENT') or ('--no-log-stderr' in sys.argv):
    __logstream = None
else:
    __logstream = sys.stderr

mojolog = DebugStream(logstream=__logstream, logfile=__logfile)
stderr = mojolog  # DEPRECATED: old was debug.stderr.write, new is debug.mojolog.write

# create a mojolog-current symlink on systems that support it.
if (__logfile is not None) and hasattr(os, 'symlink'):
    basedir = os.path.dirname(__logfile)
    linkname = os.path.join(basedir, 'mojolog-current')
    try:
        os.unlink(linkname)  # remove any previous one
    except:
        pass
    try:
        os.symlink(__logfile, linkname)
    except OSError, le:
        le.args = (__logfile, linkname, le.args,)
        print "__logfile: %s, linkname: %s, le.args: %s" % (str(__logfile), str(linkname), str(le.args),)
        raise le

    del basedir, linkname


def rotate_mojolog(doq=None, delay=87600):
    """this only works for log files we're actually writing to directly"""
    if doq:
        doq.add_task(rotate_mojolog, delay=delay, kwargs={'doq': doq, 'delay': delay})
    if ('--no-log-file' in sys.argv):
        return
    if sys.platform == 'win32' or ('--rotated-log' in sys.argv):
        logfile = generate_mojolog_filename()
        mojolog.rotate_logfile(logfile)
        cleanup_old_mojologs(int(confman['MOJOLOG']['MAX_ROTATED_LOG_AGE_IN_HOURS']), logfile)
        # create a mojolog-current symlink on systems that support it.
        if hasattr(os, 'symlink'):
            basedir = os.path.dirname(logfile)
            linkname = os.path.join(basedir, 'mojolog-current')
            try:
                os.unlink(linkname)  # remove any previous one
            except:
                pass
            os.symlink(logfile, linkname)
            del basedir, linkname


########################################## HERE IS THE humanreadable.py PART OF mojostd.py

from humanreadable import hr

########################################## HERE IS THE idlib.py PART OF mojostd.py

from idlib import make_id, make_ascii_id, canonicalize, equal, equals, make_new_random_id, string_to_id, id_to_abbrev, is_sloppy_id, is_mojosixbitencoded_id, is_ascii_id, is_binary_id, sloppy_id_to_bare_binary_id, to_binary, to_mojosixbit, new_random_uniq, identifies, newRandomUniq, new_random_uniq

########################################## HERE IS THE DataTypes.py PART OF mojostd.py

from DataTypes import UNIQUE_ID, ASCII_ID, ANY, ASCII_ARMORED_DATA, BINARY_SHA1, INTEGER, NON_NEGATIVE_INTEGER, MOD_VAL, INTEGER, ListMarker, OptionMarker, NONEMPTY, NOT_PRESENT, STRING, BadFormatError, checkTemplate, BOOLEAN

from MojoErrors import MojoMessageError

########################################## HERE IS THE SEXP.py PART OF mojostd.py

def stringToDict(string) :
    """
    @deprecated in favor of `mencode.mdecode()'
    """
    try:
        return mencode.mdecode(string)
    except mencode.MencodeError:
        raise IllFormedError, 'mdecode error; cannot mdecode %s' % hr(string)

def dictToString(dict) :
    """
    @deprecated in favor of `mencode.mencode()'
    """
    return mencode.mencode(dict)

def listToDict(list):
    """
    @deprecated in favor of .. well, you don't have to call anything at all since somebody else already used `mencode.mencode()'
    """
    if not list:
        return {}  # empty list -> empty dict
    else:
        dict = {}
    
        # maxwidth is how many characters it takes to write the index number of the largest item
        # in this list.
        maxwidth = len(str(len(list)-1))

        i = 0
        for item in list:
            key = string.zfill(str(i), maxwidth)
            dict[key] = item
            i = i + 1


        return dict
        

def dictToList(dict):
    """
    All keys must be of the same width, and that width must be the smallest width sufficient to
    encode the largest key.  Keys must be integers, starting at 0 and incrementing.

    @deprecated in favor of .. well, you don't have to call anything at all since somebody else already used `mencode.mdecode()'
    """
    if type(dict) != types.DictType :
        raise SEXPError, 'expected dict, got %s :: %s' % (`dict`, `type(dict)`)
    def checkIsNum(str):
        for char in str:
            if not char in "0123456789":
                raise IllFormedError

    if not dict:
        return []
    list = []

    keys = dict.keys()
    keys.sort()

    width = len(keys[0])
    checkIsNum(keys[0])
    if int(keys[0]) != 0:
        raise IllFormedError

    i = 0
    for key in keys:
        if width != len(key):
            raise IllFormedError, "dict: " + `dict` + " doesn't encode an MojoList."

        checkIsNum(key)
        if int(key) != i:
            raise IllFormedError

        i = i + 1

        list.append(dict[key])

    return list


mojo_test_flag = 0

def test_stringToDict_raise_illformed_error_on_illformed_sexp():
    ILLFORMED_DEMO_CONVERSATION_MANAGER_SERIALIZED='((14:session keeper219:((22:private key serialized186:MIGIAgEAAhoAzpZ2__0B8xQekXKD2nOxGwWGilEr1BLm1QIBAwIZIm5pKqoq_divwuhrSkdhFk3m06RILKxPHQINDbRKt_hI0xM7oEI6PwINDxMf3TnUwWQ_J8bR6wINCSLceqWF4gzSatbRfwINCgy_6NE4gO1_b9nhRwINAdaArpMfY-8_DY6EQ))))'
    try:
        stringToDict(ILLFORMED_DEMO_CONVERSATION_MANAGER_SERIALIZED)
    except IllFormedError:
        return "success" # You pass the test.

    assert false, "you should have raised an ill-formed error"

def test_stringToDict_must_catch_bounds_error():
    killerstring='((4'
    try:
        stringToDict(killerstring)
    except IllFormedError:
        pass
    else:
        assert false, "stringToDict() must catch bounds error!"


def manually_test_internal_dictToString_speed(dictToString = dictToString) :
    # this was used to test the speed of various dictToString implementations,
    # the StringIO method won as it was the fastest on all but small dicts where
    # the speed of this call will be dwarfed by other things.  27/jun/2000
    import time
    d = { 'spam' : { 'morespam' : 'eggs', 'foo' : 'bar' } }
    calls = 4000
    start = time.time()
    for x in xrange(0, calls) :
        dictToString(d)
    stop = time.time()
    print 'TIME: small dict w/ subdict: %1.2f times per second' % ((1/(stop - start))*calls)
    foo = { 'newspam' : { 'morespam' : 'eggs', 'foo' : 'bar' } }
    for x in xrange(0, 500) :
        d[str(x)] = foo
    calls = 20
    start = time.time()
    for x in xrange(0, calls) :
        dictToString(d)
    stop = time.time()
    print 'TIME: many item dict: %1.2f times per second' % ((1/(stop - start))*calls)
    d = { 'spam' : { 'morespam' : 'eggs', 'foo' : 'bar' }, 'data1': 'Eggs'*2000, 'data2': 'Spam'*2000 }
    calls = 100
    start = time.time()
    for x in xrange(0, calls) :
        dictToString(d)
    stop = time.time()
    print 'TIME: big item dict: %1.2f times per second' % ((1/(stop - start))*calls)
    d = { 'spam' : { 'morespam' : 'eggs', 'foo' : 'bar' }, 'data': 'Spam'*64000 }
    calls = 100
    start = time.time()
    for x in xrange(0, calls) :
        dictToString(d)
    stop = time.time()
    print 'TIME: bigger item dict: %1.2f times per second' % ((1/(stop - start))*calls)
    pass


class SEXPError(StandardError):
    pass

class IllFormedError(SEXPError):
    pass




########################################## HERE IS THE cryptutil.py PART OF mojostd.py

class cryptutilError(StandardError):
    pass
    
class OAEPError(cryptutilError):
    pass

def xor(str1, str2):
    """
    @precondition `str1' and `str2' must be of the same length.: len(str1) == len(str2): "str1: %s, str2: %s" % (hr(str1), hr(str2))
    """
    assert len(str1) == len(str2), "`str1' and `str2' must be of the same length." + " -- " + "str1: %s, str2: %s" % (hr(str1), hr(str2))

    try:
        # This should be faster
        import array
        if len(str1)%4 == 0:
            a1 = array.array('i',str1)
            a2 = array.array('i',str2)
            for i in range(len(a1)):
                a2[i] = a2[i]^a1[i]
        elif len(str1)%2 == 0:
            a1 = array.array('h',str1)
            a2 = array.array('h',str2)
            for i in range(len(a1)):
                a2[i] = a2[i]^a1[i]
        else:
            a1 = array.array('c',str1)
            a2 = array.array('c',str2)
            for i in range(len(a1)):
                a2[i] = chr(ord(a2[i])^ord(a1[i]))

        return a2.tostring()

    except ImportError:
        # XXX pleeeease speed me up.  (Crypto++?)  --Zooko 2000-07-29
        # Could use cStringIO, array or struct, or convert to longs
        res = ''
        for i in range(len(str1)):
            res = res + chr(ord(str1[i]) ^ ord(str2[i]))

        return res

def hmac(key, message):
    SIZE_OF_SHA1_INPUT = 64
    ipad = '\x36' * SIZE_OF_SHA1_INPUT
    opad = '\x5C' * SIZE_OF_SHA1_INPUT

    if len(key)>SIZE_OF_SHA1_INPUT:
        key = sha.sha(key).digest()

    key = key + '\000'*(SIZE_OF_SHA1_INPUT - len(key))

    a = xor(key, ipad)
    h1 = sha.sha(a + message).digest()
    b = xor(key, opad)
    h2 = sha.sha(b + h1).digest()

    return h2

def hmacish(key, message):
    hasher = sha.sha()
    hasher.update(key)
    hasher.update(message)
    hasher2 = sha.sha()
    hasher2.update(message)
    hasher2.update(hasher.digest())
    return hasher2.digest()

def mgf1(seed, intendedlength):
    """
    Mask Generation Function 1 MGF1 from PKCS #1 v2.
    """
    # I _think_ that MGF1 is the same as our HashRandom.SHARandom()...
    # XXX !!! We should verify this hypothesis...  --Zooko 2000-07-29
    s = HashRandom.SHARandom(seed)
    return s.get(intendedlength)

def oaep(m, emLen, p=""):
    """
    OAEP from PKCS #1 v2.  Not bitwise correct -- different encodings, length granularity, etc.

    Remember that modvals prefer an input of size SIZE_OF_MODULAR_VALUES, where oaep() returns a
    padded thingie of size SIZE_OF_MODULAR_VALUES - 1.  The thing to do is prepend a 0 byte
    before passing to modval.

    @param m the message to be encoded
    @param emLen the intended length of the padded form (should be MojoConstants.SIZE_OF_MODULAR_VALUES)
    @param p encoding parameters; we use empty string

    @precondition The length of `p' must be less than or equal to the input limitation for SHA-1.: len(p) <= ((2^61)-1): "p: %s" % hr(p)
    @precondition `emLen' must be big enough.: emLen >= (2 * MojoConstants.SIZE_OF_UNIQS) + 1: "emLen: %s, MojoConstants.SIZE_OF_UNIQS: %s" % (hr(emLen), hr(MojoConstants.SIZE_OF_UNIQS))
    @precondition The length of `m' must be small enough to fit.: len(m) <= (emLen - (2 * MojoConstants.SIZE_OF_UNIQS) - 1): "emLen: %s, MojoConstants.SIZE_OF_UNIQS: %s" % (hr(emLen), hr(MojoConstants.SIZE_OF_UNIQS))
    """
    assert len(p) <= ((2^61)-1), "The length of `p' must be less than or equal to the input limitation for SHA-1." + " -- " + "p: %s" % hr(p)
    assert emLen >= (2 * MojoConstants.SIZE_OF_UNIQS) + 1, "`emLen' must be big enough." + " -- " + "emLen: %s, MojoConstants.SIZE_OF_UNIQS: %s" % (hr(emLen), hr(MojoConstants.SIZE_OF_UNIQS))
    assert len(m) <= (emLen - (2 * MojoConstants.SIZE_OF_UNIQS) - 1), "The length of `m' must be small enough to fit." + " -- " + "emLen: %s, MojoConstants.SIZE_OF_UNIQS: %s" % (hr(emLen), hr(MojoConstants.SIZE_OF_UNIQS))

    hLen = MojoConstants.SIZE_OF_UNIQS

    # mojolog.write("mojoutil.oaep(): -- -- -- -- -- -- m: %s\n" % hr(m))
    # mojolog.write("mojoutil.oaep(): -- -- -- -- -- -- emLen: %s\n" % hr(emLen))
    ps = '\000' * (emLen - len(m) - (2 * hLen) - 1)
    # mojolog.write("mojoutil.oaep(): -- -- -- -- -- -- ps: %s\n" % hr(ps))
    pHash = sha.new(p).digest()
    db = pHash + ps + '\001' + m
    # mojolog.write("mojoutil.oaep(): -- -- -- -- -- -- db: %s\n" % hr(db))
    seed = randsource.get(hLen)
    dbMask = mgf1(seed, emLen - hLen)
    maskedDB = xor(db, dbMask)
    seedMask = mgf1(maskedDB, hLen)
    maskedSeed = xor(seed, seedMask)
    em = maskedSeed + maskedDB

    assert len(em) == emLen

    # mojolog.write("mojoutil.oaep(): -- -- -- -- -- -- em: %s\n" % hr(em))
    return em

def oaep_decode(em, p=""):
    """
    Remember that modvals output cleartext of size SIZE_OF_MODULAR_VALUES, where oaep() needs a
    padded thingie of size SIZE_OF_MODULAR_VALUES - 1.  The thing to do is pop off the prepended
    0 byte before passing to oaep_decode().  (Feel free to check whether it is zero and raise a
    bad-encoding error if it isn't.)

    @param em the encoded message
    @param p encoding parameters; we use empty string

    @precondition The length of `p' must be less than or equal to the input limitation for SHA-1.: len(p) <= ((2^61)-1)
    """
    assert len(p) <= ((2^61)-1), "The length of `p' must be less than or equal to the input limitation for SHA-1."

    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- em: %s\n" % hr(em))

    if len(em) < (2 * MojoConstants.SIZE_OF_UNIQS) + 1:
        raise OAEPError, "decoding error: `em' is not long enough."

    hLen = MojoConstants.SIZE_OF_UNIQS
    maskedSeed = em[:hLen]
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- maskedSeed: %s\n" % hr(maskedSeed))
    maskedDB = em[hLen:]
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- maskedDB: %s\n" % hr(maskedDB))
    assert len(maskedDB) == (len(em) - hLen)
    seedMask = mgf1(maskedDB, hLen)
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- seedMask: %s\n" % hr(seedMask))
    seed = xor(maskedSeed, seedMask)
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- seed: %s\n" % hr(seed))
    dbMask = mgf1(seed, len(em) - hLen)
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- dbMask: %s\n" % hr(dbMask))
    db = xor(maskedDB, dbMask)
    # mojolog.write("mojoutil.oaep_decode(): -- -- -- -- -- -- db: %s\n" % hr(db))
    pHash = sha.sha(p).digest()

    pHashPrime = db[:hLen]

    # Now looking for `ps'...
    i = hLen
    while db[i] == '\000':
        if i >= len(db):
            raise OAEPError, "decoding error: all 0's -- no m found"

        i = i + 1

    if db[i] != '\001':
        raise OAEPError, "decoding error: no 1 byte separator found before m -- db: %s, i: %s, db[i:]: %s\n" % (str(db), str(i), str(db[i:]))

    m = db[i+1:] # This is here instead of after the check because that's the way it is written in the PKCS doc.  --Zooko 2000-07-29

    if pHash != pHashPrime:
        raise OAEPError, "decoding error: pHash: %s != pHashPrime: %s" % (hr(pHash), hr(pHashPrime))

    return m

def get_rand_lt_n(seed, n):
    """
    @param n a modval

    This function can take an average of 2^(K+1) time, where K is the number of leading 0 bits
    in the most significant places in `n'.  In all of our current code, K == 0 (modvals are
    always chosen to have a 1-bit in the most significant place.)
    """
    old = n.get_value()

    r = HashRandom.SHARandom(seed)
    x = r.get(len(n.get_modulus()))

    while modval.verify_key_and_value(n.get_modulus(), x) != None:
        x = r.get(len(n.get_modulus()))

    return x

def get_rand_lt_n_with_prepended_0(seed, n):
    """
    @param n a modval
    """
    r = HashRandom.SHARandom(seed)
    return '\000' + r.get(len(n.get_modulus()) - 1)

########################################## HERE IS THE canon.py PART OF mojostd.py

def _canon(numstr, size):
    """
    @param numstr the string representation of an integer which will be canonicalized
    @param size the size in 8-bit bytes (octets) that numbers of this kind should have;  This
        number should almost always be MojoConstants.SIZE_OF_UNIQS or
        MojoConstants.SIZE_OF_MODULAR_VALUES

    @return the canonical version of `numstr' for numbers of its type

    @precondition `numstr' must be a string.: type(numstr) == types.StringType: "numstr: %s :: %s" % (hr(numstr), `type(numstr)`)
    @precondition `numstr', not counting leading zeroes, is not too large.: len(strip_leading_zeroes(numstr)) <= size: "numstr: %s" % hr(numstr)
    """
    assert type(numstr) == types.StringType, "precondition: `numstr' must be a string." + " -- " + "numstr: %s :: %s" % (hr(numstr), `type(numstr)`)
    assert len(strip_leading_zeroes(numstr)) <= size, "precondition: `numstr', not counting leading zeroes, is not too large." + " -- " + "numstr: %s" % hr(numstr)

    if len(numstr) >= size:
        return numstr[len(numstr) - size:]

    return operator.repeat('\000', size - len(numstr)) + numstr

def strip_leading_zeroes(numstr):
    """
    @param numstr the string to be stripped

    @return `numstr' minus any leading zero bytes

    @precondition `numstr' must be a string.: type(numstr) == types.StringType: "numstr: %s :: %s" % (hr(numstr), `type(numstr)`)
    """
    assert type(numstr) == types.StringType, "precondition: `numstr' must be a string." + " -- " + "numstr: %s :: %s" % (hr(numstr), `type(numstr)`)

    if len(numstr) == 0:
        return numstr

    # When we are done `i' will point to the first non-zero byte.
    i = 0

    while (i < len(numstr)) and (numstr[i] == '\000'):
        i = i + 1
        
    return numstr[i:]

def is_canonical(astr, length, StringType=types.StringType):
    if type(astr) is not types.StringType:
        return 0 # false
    return len(astr) == length

def is_canonical_modval(astr):
    """
    Return `true' if and only if `astr' is in canonical format for modular values encoded into
    string form.

    @memoizable
    """
    return is_canonical(astr, MojoConstants.SIZE_OF_MODULAR_VALUES)

def is_canonical_uniq(astr):
    """
    Return `true' if and only if `astr' is in canonical format for "uniq" strings.

    @memoizable
    """
    return is_canonical(astr, MojoConstants.SIZE_OF_UNIQS)

def test_strip_leading_zeroes():
    str = '\000'
    res = strip_leading_zeroes(str)
    assert res == ""
    pass

def test_strip_leading_zeroes():
    str = '\000\000'
    res = strip_leading_zeroes(str)
    assert res == ""
    pass
    
def test_strip_leading_zeroes():
    str = '\000\000A'
    res = strip_leading_zeroes(str)
    assert res == 'A'
    pass
    
def test_strip_leading_zeroes():
    str = 'B\000\000A'
    res = strip_leading_zeroes(str)
    assert res == str
    pass

def test__canon():
    str = '\000'
    res = _canon(str, 2)
    assert res == '\000\000'

def test_canon():
    str = '123'
    res = _canon(str, 128)
    assert res != '123'
    assert res == "\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000123"

def test_canon_rejectsTooLarge():
    str = '123'
    try:
        _canon(str, 2)
    except AssertionError:
        return

    assert false

def test_canon_tooManyLeadingZeroes():
    str = '\00023'

    assert _canon(str, 2) == '23'

def test_canon_same():
    str = '23'

    assert _canon(str, 2) == '23'

def test_canon_empty():
    str = ''

    assert _canon(str, 2) == '\000\000'


########################################## HERE IS THE confutils.py PART OF mojostd.py

"""
General notes:
-   The typical way to use this module is like this:
# Begin Code Example:
from confutils import confman
x = confman[key]
confman[key] = x
confman.save()
# End Code Example.

-   Note, when assigning to confman, make sure not to reassign a dict reference, for instance
    don't do this:
# Begin Code Example:
# Here confman["PATH"] is a subdict of confman
confman["PATH"] = mypathdict
# End Code Example.

    Instead, do this:

# Begin Code Example:
import mojoutil
mojoutil.recursive_dict_update(confman["PATH"], mypathdict)
# End Code Example.

-   If you don't assign any values to confman, you may omit the confman.save() call.
    If you do assign values, and do not call confman.save(), they will not be written to
    the file.

-   If you'd like to add your own default value, as of CVS revision 1.4 of this file:
    -   If it is a path, add it in the '^### Configuration Defaults' section, '^## File System Paths' subsection
        in the form of 'confdefaults["PATH"][ <key name> ] = <path name>'.  If it is a directory, the keyname
        must end with '_DIR', if it is not a directory it must not end with that string.
    - Other data is a free for all.  Add it in the '^### Configuration Defaults' section, '^## Application Data'
        subsection.  There is a call to mojoutil.recursive_dict_update.  Add you're arbitrary string-only dict
        to the second argument.  (Follow the existing example, it's pretty straight forward.)
    - Add a comment containing 'XXX CONFIG' to tag code for later review by the Nefarious Junior Code Monkey.
        (Note: Although his trainers do a good job of getting him to perform the "assimilate into confutils" job,
        its best for coders to do this themselves, so he can work on his other circus acts.)

-   Necessary To Do:
    ?

-   Wishlist:
    -   Persistence: No need to call save(), if a change is made the file is updated automagically.
    -   Atomicity: Multiple processes can access and assign configuration values without dealing
                with locking directly.  This might not be necessary if we ensure only one process
                accesses the configuration data at any time (say, if all plugins use the same confutils
                interface).

-   You can grep for "PLATFORM NOTE" to find comments detailing possible platform-dependency
    issues.
"""

### Constants:
# As the heading implies, these values should not be altered.

# keep these as valid VersionNumbers, our code will use that to
# check for later versions of the software from the bootpage.
from EGTPVersion import EGTP_VERSION_STR

# XXX until this is autodetected, don't have it misreport
import evilcryptopp
if hasattr(evilcryptopp, "cryptopp_version"):
    CRYPTOPP_VERSION_STR = evilcryptopp.cryptopp_version
else:
    CRYPTOPP_VERSION_STR = "unknown"

## Platform Detection:
# Supported platforms:
# The format of this dict is a key identifying a general platform, and a
# tuple value representing specific platform strings which get mapped into
# general identifier.  If you need a more specific identification,
# use sys.platform.

platform_map = {
    "linux-i386": "linux", # redhat
    "linux-ppc": "linux",  # redhat
    "linux2": "linux",     # debian
    "win32": "win32",
    "irix6-n32": "irix",
    "irix6-n64": "irix",
    "irix6": "irix",
    "openbsd2": "bsd",
    "freebsd4": "bsd",
    "netbsd1": "bsd",
    }

# Platform information:
platform = sys.platform
try:
    platform = platform_map[platform]
except KeyError:
    # To be cautious, if platform is not in platforms, warn the developer.
    # (By release time this should gracefully explain to the user that the
    # platform is not supported, but of course that will never happen.  -Nate
    mojolog.write("WARNING: %s is not a supported platform.\n" % platform)
    mojolog.write("Supported platforms include:\n" + str(platform_map))


### Configuration Defaults:
#
# NOTE: To see confdefaults in a precise way, run "python confutils.py".
#
# confdefaults contains the "hard-coded" defaults of all user-configurable data.
# Note that if defaults does not define a key AND the user doesn't define a key,
# then accessing it will result in an exception.  If a default is defined for
# all accessed data, then programming becomes much clearer (because less
# exceptions must be handled).  Also note that we may _want_ an exception for
# cases such as keys.
#
# Note, applications should create a ConfManager, cm, and call cm.load(),
# then access cm.dict, rather than confdefaults.  This ensures that values
# configured in the configuration file are used, rather than the defaults.
confdefaults = {}

## File System Paths:
# confdefaults["PATH"] is a dict which contains all important config file/data file paths.
# NOTE: All of these paths are absolute and platform independent.
confdefaults["PATH"] = {}

confdefaults["PATH"]["HOME_DIR"] = HOME_DIR

### Broker paths:
# BROKER_DIR is the root directory of all client-side configuration and data files.
# For now we just use the value of the environment variable "EVILCONFDIR",
# but someday we want code that abstracts the platform even more, in order to make
# installation and setup of the Broker as smooth as possible.
# mojolog.write("HELLO os.environ: %s\n" % `os.environ.items()`)
# mojolog.write("HELLO confdefaults: %s\n", args=(confdefaults,))
# mojolog.write("HELLO sys.path: %s\n" % `sys.path`)

confdefaults["PATH"]["BROKER_DIR"] = BROKER_DIR

# SAVE_TO_DISK_DIR is the path where the 'save to disk' download link
# will put downloaded files and directories:
confdefaults["PATH"]["SAVE_TO_DISK_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["HOME_DIR"], "downloads")
    )


# For now BROKER_CONF is the path of the single file which contains Broker configuration
# info.  Later we may have multiple files (such as system-level vs. user-level, etcetera).
# PLATFORM NOTE: All supported platforms must support 4 character extensions.
#                (So DOS is out, damn!  Mac?)  This can easily be changed.
confdefaults["PATH"]["BROKER_CONF"] = os.path.join(confdefaults["PATH"]["BROKER_DIR"], "broker.conf")

# MIME_TYPES is the path of the MIME types file:
confdefaults["PATH"]["MIME_TYPES"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "mime.types")
    )

# MOJOSTASH_DIR is the directory used to store your withdrawn mojo tokens!
confdefaults["PATH"]["MOJOSTASH_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "stash")
    )

# DOWNLOAD_CACHE_DIR is the directory used by localblockstore and the like:
confdefaults["PATH"]["DOWNLOAD_CACHE_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "download_cache")
    )

# BBL_SUBSCRIBER_DIR is the directory used by BadBlockListSubscriber:
confdefaults["PATH"]["BBL_SUBSCRIBER_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "bbl_subscriber")
    )

# CONTENT_TRACKER_DB_DIR is used in ContentTrackerEGTP.py:
confdefaults["PATH"]["CONTENT_TRACKER_DB_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "contenttracker")
    )

# CONTENT_TYPEDEF_DIR is used by clients and content trackers for
# storing content tracker content type definition (".mct") xml files.
confdefaults["PATH"]["CONTENT_TYPEDEF_DIR"] = os.path.normpath(
        os.path.join("${EVILDIR}", "contenttypes")
    )

# MOJO_TRANSACTION_MANAGER_DB_DIR is used for storing persistent info
# about messages in MojoTransaction.py.
confdefaults["PATH"]["MOJO_TRANSACTION_MANAGER_DB_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "mtmdb")
    )

# TMP_DIR is a general temporary directory.  File created here shouldn't expect
# to live longer than the live of the process.
confdefaults["PATH"]["TMP_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "temporary")
    )

# PID_FILE is a file containing the process identifiers (platform specific) of a running Broker.
# This is used to ensure only one Broker runs at any time.
# XXX I'm not sure if this is currently used.   -Nathan 2000-07-20 
confdefaults["PATH"]["PID_FILE"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "processfile")
    )

confdefaults["PATH"]["WEBROOT_DIR"] = os.path.normpath(
        os.path.join("${EVILDIR}", "localweb", "webroot")
    )

confdefaults["PATH"]["WEB_TEMPLATE_DIR"] = os.path.normpath(
        os.path.join("${EVILDIR}", "localweb", "templates")
    )

confdefaults["PATH"]["INTRO_PAGE_v2"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "intropage.html")
    )

confdefaults["PATH"]["BASE_URL_FILE"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "base.url")
    )

#  For MetaTrackers:
confdefaults["PATH"]["BOOT_PAGE"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "bootpage.txt")
    )

confdefaults["PATH"]["QUICKSTART"] = os.path.normpath(
        os.path.join("${EVILDIR}", "quickstart.txt")
    )

readmename = 'README'
if sys.platform == 'win32':
    readmename = 'README.txt'
confdefaults["PATH"]["README_FILE_v2"] = os.path.normpath(
        os.path.join("${EVILDIR}", readmename)
    )

confdefaults["PATH"]["FAQ_FILE"] = os.path.normpath(
        os.path.join("${EVILDIR}", "faq.txt")
    )

confdefaults["PATH"]["MOJOMOD_DIR"] = os.path.normpath(
        os.path.join(confdefaults["PATH"]["BROKER_DIR"], "MojoMods")
    )


def round_to_positive_int_with_min(fval, minval=1):
    return max(minval, int(float(fval) + 0.5))


def gen_per_kb_price_dict(onekbprice, scalingfactor=0.95) : # XXX Shouldn't this be in pricelib?  --Zooko 2000-09-02
    """
    Generate a scaled price dict for block server pricing based off on
    the one kilobyte price.  See the algorithm for details.
    """
    power = 1
    resultdict = {str(1): str(round_to_positive_int_with_min(onekbprice))}
    for size in (2,4,8,16,32,64,128) :
        resultdict[str(size)] = str( round_to_positive_int_with_min(size * (0.95**power) * onekbprice) )
        power = power + 1
    return resultdict


## Application Data:
dictutil.recursive_dict_update(confdefaults,
        {
            "MAX_VERBOSITY" : "2",
            "EGTP_VERSION_STR" : EGTP_VERSION_STR,
            
            # for General Preferences
            "AUTO_LAUNCH_BROWSER": "yes",
            "UI_REFRESH_RATE" : str(20),
            "UI_SHOW_CONFIG_DEFAULTS" : "yes",
            "MOJO_WARNING_ON": "no",
            "MOJO_WARNING": str(50000),
            "CONN_SPEED_IN" : "56",
            "CONN_SPEED_OUT" : "56",
            "GOT_MOJO" : "no",
            "USE_ROUTE_TO_GET_WIN32_IPADDR": "no",   # see ipaddresslib

            # wxBroker settings
            "WXBROKER": {
                "SHOW_STATUS_BAR":      "no",
                "MAIN_WINDOW": {
                    # -1 for either of these means "center the window"
                    "POS_X":            str(-1),
                    "POS_Y":            str(-1),
                    "SIZE_X":           str(640),
                    "SIZE_Y":           str(400),
                    "IS_MAXIMIZED":     "yes",
                },
            },
                    
                
            # UI usability kludges:
            "DUPLICATE_PROCESS_SANITY_CHECK": "no", # Check for another Broker running. # This makes my broker hang sometimes on Linux so I'm defaulting it off.  --Zooko 2001-10-24
            "DUPLICATE_UI_SPAWN": "no", # If there's a another Broker this process launches a UI to the other then this exits.

            # these specify which services the Broker should run
            "YES_NO": {
                # for Server Settings
                "RUN_LOCALHOST_GATEWAY": "yes",
                "RUN_WXBROKER":          "no",
                "RUN_META_TRACKER":      "no",
                "RUN_BLOCK_SERVER":      "yes",
                "RUN_CONTENT_TRACKER":   "no",

                "RUN_RELAY_SERVER":      "no",
                "SERVE_USING_A_RELAY":   "no",

                # If true TCP transport will be used regardless of the IP address, or any other factors.
                # Relay will not be used.
                "FORCE_TCP_TRANSPORT": "no",

                # ie: should the web server bind to '' instead of 127.0.0.1?
                "ALLOW_ACCESS_FROM_OUTSIDE_LOCALHOST": "no",

                "BLOCK_SERVER_ALLOWS_PUBLISHING": "yes",
            },

            "PUBLICATION": {
                # the K of M to use for information dispersal while publishing
                "SHARES_NEEDED": str(12),
                "SHARES_GENERATED": str(24),
                # this should be a power of two.
                "MAX_SHARE_SIZE": str(65536),
                # the maximum piece/chunk size is MAX_SHARE_SIZE * SHARES_NEEDED, it should be kept <= 2 MB for sanity
                "MIN_SHARE_SIZE": str(1024),
                # the minimum piece/chunk size is MIN_SHARE_SIZE * SHARES_NEEDED, it should be kept <= 2 MB for sanity
            },

            # if enabled, this broker will withstand extended token server outages much better
            'KEEP_FUNCTIONING_WHILE_TS_IS_DOWN': "yes",

            # this is higher than the old 7 default now that we have fast relay since
            # polling's primary job is to keep the TCP connection open and to "register"
            # with the relay server so that it fast-sends messages to us if the connection
            # is open.
            "RELAY_SERVER_POLL_PERIOD_v2":  str(15),
            # fail over to a new relay server if polling fails
            # FAILURE_LIMIT times in FAILURE_WINDOW_SECS.
            "RELAY_SERVER_POLL_FAILURE_LIMIT": str(4),
            "RELAY_SERVER_POLL_FAILURE_WINDOW_SECS_v2": str(900),
            # we don't use dynamic timeouts when polling as it tends be too nice and make the timeout be a few
            # seconds which fails way too easily when the broker gets busy downloading or wholesaling.
            "RELAY_SERVER_POLL_TIMEOUT": str(30),

            # MojoTransaction will try and use these relay servers first
            "PREFERRED_RELAY_SERVER_ID_LIST": {
                # a SEXP listToDict style list of b2a encoded ids goes here
            },

            "BadBlockSubscriptionList": {}, # A list of mtm id's of BadBlockListServers to subscribe to.

            "CLIENT_PORT": str(4004),
            # See confdefaults["PATH"]["MIME_TYPES_PATH"]
            # default mime type is rarely used -- only if neither ctype nor filename give us a good hint
            # Note that most browsers will probably display plain text just fine if the MIME type is "text/html", but not so pretty the other way around.
            # (I tested this theory with Netscape 4.76, lynx 2.8.3rel.1 (23 Apr 2000), and links (version unknown).  --Zooko 2000-12-14)
            "DEFAULT_MIME_TYPE": "text/html",
            # The max amount of reassembled pieces/chunks that will be cached for easy access in RAM.
            "PIECE_CACHE_SIZE_v2": str(4*1024*1024),
            "PIECE_CACHE_TIMEOUT": str(15*60),
            # all blocks that you download will be stored in a localblockstore with this maximum
            # size.  Set this to zero if you wish to not cache downloaded blocks for any reason.
            "DOWNLOADED_BLOCK_DISK_CACHE_MEGABYTES": str(15),
            # Only set this if you want to announce your IP address as
            # something other than what ipaddresslib would otherwise return.
            # (useful for hackers who run things behind a NAT/masq firewall
            # with a port redirected through it)
            "IP_ADDRESS_OVERRIDE" : "",
            "IP_ADDRESS_DETECTOR_HOST": "198.11.16.136",    # if Yahoo's DNS is down, the internet might as well no longer exist
            # The number of TCP connections to hold open in case you deal with that counterparty
            # again.  I'm not sure what the best number here is.  Maybe 0.  But if you have
            # frequent traffic, perhaps with relay servers, you might benefit from a higher
            # number (like 5) to keep connections open to your most frequent
            # counterparties.
            # Or, heck.  Maybe 512 would be good.
            "TCP_MAINTAINED_CONNECTIONS": "32",
            # The total maximum number of TCP connections for this Broker.  If there are this
            # many _active_ connections then initiation of new transactions will fail.  This
            # number can probably be pretty high because connections are not considered "active"
            # unless they are actually sending or receiving a message at that moment.  So
            # probably even if this number is a high number like 128, your connections will be
            # cleaned up down to your preferred number (TCP_MAINTAINED_CONNECTIONS) as soon as
            # each connection is done sending the message.  If you are on such a slow connection
            # that a message takes a long time to squeeze through, then you should never have
            # opened 128 connections in the first place.
            "TCP_MAX_CONNECTIONS": "512",
            # inactivity timeout for our TCP connections in seconds;  We never time-out a
            # connection if we want it because we are either expecting a reply, or maintaining a
            # connection with a frequently-used counterparty.
            "TCP_TIMEOUT": "600",
            # If a call to connect() hasn't succeeded after this many seconds, consider it a failure.
            # (this is required on windows as asyncore does not notify if a connect() call failed)
            "TCP_CONNECT_TIMEOUT": "30",

            # The only currently known block fetching strategy is "FindBeforehandBlockFetcher".
            "BLOCK_FETCHING_STRATEGY_v2": "FindBeforehandBlockFetcher",

            "DOWNLOAD_MONITOR": {
                "SHOW_TOO_MUCH_DETAIL_v2": "yes",
            },

            # How often to prune the queue of incoming requests.
            "REQUEST_HANDLER_PRUNE_DELAY": str(90),
            # the maximum number of seconds we will hold an incoming request for later processing when
            # we have the resources before dropping it on the floor.
            "REQUEST_HANDLER_MAX_DEPTH": str(256),

            "MOJOLOG": {
                # when log rotation is enabled, all log files older than this will be deleted
                # (win32 uses it by default; unix brokers must be run with '--rotated-log')
                "MAX_ROTATED_LOG_AGE_IN_HOURS": str(24*4),
                # if running with log rotation, how often should the logs be rotated
                "LOG_ROTATION_FREQUENCY_IN_HOURS": str(24),
            },

            # configuration values for MetaTrackerLib - the meta tracker
            # interface and response cache.
            "METATRACKERLIB" : {
                # this is the timeout before allowing another similar meta
                # tracker query to be sent if we already have more than MIN 
                # usable results in our cache. -greg
                # Doubled from 240 to 480 on 10-oct-2000 to help ease meta tracker load
                "SECONDS_BEFORE_ALLOWING_A_RETRY_LOOKUP_v4": str(480),
                # if we have this many cached results (and the user didn't specify a
                # greater minimum) we won't try a new list spam servers message).
                # XXX don't make this big; it is used even after filtering results for their mask
                "MIN_CACHED_RESULTS_TO_PREVENT_RETRY_LOOKUP_v4": str(2),
                # XXX once we have fast fail toss out of contact info we can
                # raise or nuke this (we also need to make the cache persistant)
                "CACHE_INFO_TIMEOUT": str(6000),
                # keep any client from hammering the bootpage in bad failure modes...
                "MIN_TIME_BETWEEN_BOOTPAGE_RELOADS": str(90),
                # maximum number of meta trackers to ask for a particular counterparty's contact info
                "MAX_TRACKERS_TO_QUERY_FOR_ID": str(50),
                "SAVED_CACHE_FILE": os.path.join(confdefaults["PATH"]["BROKER_DIR"], "saved_metainfo.pickle"),
                "SECONDS_BETWEEN_SAVE": str(800),
                "TIME_BETWEEN_EXTRA_CONTACT_REFRESH" : str(300),
                "NUM_EXTRA_CONTACTS" : str(3)
            },

            "USE_MOJOID_IN_DOWNLOAD_LINKS": "yes",   # should search result Download http links use the short mojoid or the full dinode

            # configuration values for the user interaction with
            # content trackers when searching or submitting content
            "CONTENTTRACKER_CLIENT" : {
                "TYPEDEF_PATH" : os.path.normpath(
                    os.path.join(
                        confdefaults["PATH"]["BROKER_DIR"], "contenttypes")),
    
                # this is highish now that we have incremental search results
                "INDIVIDUAL_QUERY_TIMEOUT_v3": str(300),
                # on submissions, chances are its really accepted even if we don't hear the response quickly so don't wait long
                "INDIVIDUAL_SUBMIT_TIMEOUT": str(12),
                "MAX_QUERIES_AT_ONCE_v5": str(8),
                # the minimum and maximum number of content trackers a search will try to query
                "SEARCH_QUERY_LIMITS": {
                    "MIN": str(15),
                    "MAX": str(35),
                },
                # min and max number of content trackers to search for a mojo id -> dinode mapping on
                "MOJOID_QUERY_LIMITS": {
                    "MIN": str(20),
                    "MAX": str(100),
                },
                # configuration for the content tracker "usefulness" handicapper
                "HANDICAPPER": {
                    # extra cost of a never-before-used content tracker
                    # (XXX this would be much better if it were not configged but computed to be the average or
                    # median of all recently known content trackers.)
                    "DEFAULT": str(250),
                    # a content tracker's percentage of no match/failure responses is multiplied by this
                    "FAILURE_RATIO_WEIGHT": str(300),
                    # used as the log base when weighting avg. number of responses returned.
                    "NUMRESULTS_LOG_BASE": str(5),
                    # multiplied by the inverse of log(avgnumresponses)+1 as a handicap to steer us towards content
                    # trackers returning more results first by adding to the handicap of those who don't
                    "NUMRESULTS_WEIGHT_v2": str(40),
                },
            },

            # If this is the empty string "" a port is dynamically found, else it
            # must be an explicit port number.
            "TRANSACTION_MANAGER_LISTEN_PORT": "",
            # If TRANSACTION_MANAGER_PICKY_PORT then it will fail if it can't bind 
            # to TRANSACTION_MANAGER_LISTEN_PORT.  Else, it will just try the next
            # higher port number until it successfully binds to one.  You really 
            # do _not_ want to be picky unless a firewall or other problem prevents
            # people from connecting to arbitrary ports on your machine.
            "TRANSACTION_MANAGER_PICKY_PORT": "false",
            # If you want to announce that you are listening on a specific port, then fill this in.
            "TRANSACTION_MANAGER_ANNOUNCED_PORT": "",
            "MAX_TIMEOUT" : "3600",

            "ROOT_ID_TRACKER_CONTACT_INFO": {   # XXX leaving this in the config file for now for testing purposes - 2001-06-07
                    'connection strategies': {
                            '0': {
                                    'comm strategy type': 'crypto',
                                    'lowerstrategy': {
                                            'comm strategy type': 'TCP',
                                            'IP address': "tracker02.mojonation.net",
                                            'port number': '25333'
                                            },
                                    'pubkey': {
                                            'key values': {
                                                    'public exponent': '3',
                                                    'public modulus': 'pvqpH8n5JLH6oP439EqAsSb8WKOCMDf0CTs3n9_NldYhIRTMCV_xPtNYfTY6ofkQ8PjXgMPOwVDI3U6oy0n2Qk3nFWrzN_E9OEFm8BbdzYnygR-8bT8wwQenIuoLPXg2WUGDnrW4ywbwOfrJcT3Uf28nOzviku1DAOPLVc2w_3s',
                                                    },
                                            'key header': {
                                                    'usage': 'only for communication security',
                                                    'type': 'public',
                                                    'cryptosystem': 'RSA'
                                                    }
                                            }
                                    }
                            },
                    'services': {
                        '0' : {
                            'type': "meta tracker",
                            'hello price': str(10),
                            'lookup contact info price': str(10),
                            'list servers price': str(10),
                            'seconds until expiration': str(600),
                            },
                        },
                    },
            # from mojonation.net:25000/bootpage.txt as of 2001-06-07
            "MULTI_ROOT_ID_TRACKER_CONTACT_INFO": "[{'connection strategies': [{'comm strategy type': 'crypto', 'pubkey': {'key values': {'public exponent': '3', 'public modulus': 'pvqpH8n5JLH6oP439EqAsSb8WKOCMDf0CTs3n9_NldYhIRTMCV_xPtNYfTY6ofkQ8PjXgMPOwVDI3U6oy0n2Qk3nFWrzN_E9OEFm8BbdzYnygR-8bT8wwQenIuoLPXg2WUGDnrW4ywbwOfrJcT3Uf28nOzviku1DAOPLVc2w_3s'}, 'key header': {'usage': 'only for communication security', 'type': 'public', 'cryptosystem': 'RSA'}}, 'zlib': 'yes', 'lowerstrategy': {'comm strategy type': 'TCP', 'IP address': '64.71.128.167', 'port number': '25333'}}], 'services': [{'seconds until expiration': '600', 'list servers price': '10', 'hello price': '1', 'type': 'meta tracker', 'lookup contact info price': '10'}]}, {'connection strategies': [{'comm strategy type': 'crypto', 'pubkey': {'key values': {'public exponent': '3', 'public modulus': 'wjUrxwQdbuBWqNS-ENMgq0UZc-WKllTwmLtyS_fm3D92sgjf9-hgBXkKWXITQwKzYNGP6PqtxXIGNtafVq--Wxp72M4ob2m9PCp5pVO_gevwJGDjHImzwLtw7gwNwtsHSRPdW6HDDKXCLn6N4V_TFolbM8yqAvLqaPAiIonuf_0'}, 'key header': {'usage': 'only for communication security', 'type': 'public', 'cryptosystem': 'RSA'}}, 'zlib': 'yes', 'lowerstrategy': {'comm strategy type': 'TCP', 'IP address': '64.71.128.169', 'port number': '20301'}}], 'result': 'success', 'services': [{'seconds until expiration': '600', 'list servers price': '10', 'hello price': '1', 'type': 'meta tracker', 'lookup contact info price': '10'}]}, {'connection strategies': [{'comm strategy type': 'crypto', 'pubkey': {'key values': {'public exponent': '3', 'public modulus': 'xUslS7yfADBu4ux47nneP3Y-YJJ-RFClSpIGRknvEXf_PZ87Q11NxykGXTrNT4TkK-sF9fbPvpYcXwL9p0RWKX5pGu1ljHrA_DFtwlXoVhbVv2BIjzaCuiERn008tuK2GHleoN5OzjTw_jtHBqFaXE0DqEZ19UgGxw0G6GbJTDs'}, 'key header': {'usage': 'only for communication security', 'type': 'public', 'cryptosystem': 'RSA'}}, 'zlib': 'yes', 'lowerstrategy': {'comm strategy type': 'TCP', 'IP address': '64.71.128.168', 'port number': '25333'}}], 'services': [{'seconds until expiration': '600', 'list servers price': '10', 'hello price': '1', 'type': 'meta tracker', 'lookup contact info price': '10'}]}]",

            "COUNTERPARTY": {
                    # This is how many messages the latency is averaged over in dynamic timing collections
                    "AVERAGING_TIMESCALE_v2": "100.0",
                    "COLLECT_DYNAMIC_TIMING": "yes",
                    "USE_DYNAMIC_TIMING": "yes",
                    # used in reliability and payment computations
                    "MIN_RESPONSE_RELIABILITY_FRACTION": "0.70",
                    "MIN_NUM_MO_DIFFERENCE_FOR_RELIABILITY_CHECK": "10",
                    "MAX_NUM_MO_DIFFERENCE_BEFORE_UNRELIABLE": "2000",
                    "DEFAULT_AMOUNT_WILL_FRONT_v3": "100050",
                    #.... see common/PerformanceHandicapper.py
                    "BASE_LATENCY_HANDICAP_MULT": str(500),  # XXX
                    "BASE_THRUPUT_HANDICAP_MULT_v2": str(0.02),  # XXX
                    # this is the default weight that will be given to previous weighted statistics
                    "DEFAULT_HISTORY_WEIGHT": "0.75",
                }, 
            
            "BLOCKSERVER": {
                    "LIST_OF_BLOCKID_MASKS": {
                            "0": { "bits": str(6), },   # default number of mask bits
                        # SEXP encoded list of idmasklib masks that this block server handles
                        },
                    'TIME_BETWEEN_WHOLESALE_QUERIES': str(3600),
                    "PRICE_MAPS": {   # XXX the price map exists only for backwards compatibility for a while
                            "HAVE_BLOCK_LIST": str(4),
                            "RETRIEVE": {'1': str(11)},
                            "PUBLISH": {'1': str(5)},
                        },
                    "MIN_MEGABYTES_FREE_TO_POLL": str(5),
                    # limit block server spending per poll
                    "MAX_TO_AUTO_SPEND_ON_BLOCKS_PER_POLL_v4": str(15000),
                    # If AUTO_RECOVER_DB then whenever the block server is started it tries to
                    # fix up the database.  This is useful if you have previously killed the 
                    # block server abruptly.  It also should not hurt in normal circumstances.
                    "AUTO_RECOVER_DB": "true",

                    "STORAGE_SPACE_LIST": {
                        # this is a SEXP style listToDict format list of dicts
                        # containing PATH, MAX_MEGABYTES, SUBDIRDEPTH, and READONLY keys listing
                        # the location and size of the desired block stores.  As
                        # well as if they are normal or readonly.
                        "0" : {
                            "PATH": os.path.join(confdefaults["PATH"]["BROKER_DIR"], "blob_server"),
                            "MAX_MEGABYTES": str(500),
                            "SUBDIRDEPTH": str(3),
                            "READONLY": "no",
                        }
                    },
                    "MAX_BLOCKS_PER_WHOLESALE_RUN_v2": str(250),
                },

            'METATRACKER': {
                    "PRICES": {
                            "HELLO": str(10),
                            "LOOKUP": str(10),
                            "LIST_SERVICES": str(10),
                        },
                    # This is the maximum number of results a 'list foo' query will return
                    "MAX_QUERY_RESULTS_RETURNED": str(400),
                    # This is the number of seconds for your meta tracker to store information sent to it in
                    # a hello message.  Running servers should resend their hello info more often than this to
                    # stay known to the world.
                    "HELLO_INFO_TIMEOUT_SECS": str(30*60),
                    # This is how often our cache of hello info will be cleaned (0 means never clean/expire)
                    "HELLO_CACHE_CLEANUP_INTERVAL_SECS": str(5*60 + 17),

                    # can some more 'list servers' spam for /. crowd consumption
                    # (ie: how often to regenerate canned list servers responses for memoization reasons)
                    # NOTE: this does have the annoyance of canning a relatively empty response for this many seconds after startup...
                    "SECS_BEFORE_RECANNING_RESPONSES": str(120),
                },

            "RELAYSERVER": {
                    "MAX_MEMORY_MEGABYTES": str(6),
                    "PRICES": {
                            "POLL": str(1),
                            "FORWARD_PER_KB": str(4),
                            "RETRIEVE_PER_KB": str(10),
                        },
                },

            "CONTENTTRACKER": {
                    "MAX_RESPONSE_KILOBYTES": str(256),
                    "PRICES": {
                            "LOOKUP": str(50),
                            "SUBMIT": str(30),
                            "DOWNLOAD_TYPES": str(20),
                        },
                },
        }
    ) # dictutil.recursive_dict_update()


# On windows we have a simple gui window to act as a broker navbar.
if platform == "win32":
    confdefaults["EXTENSION_MODS"] = {
        '0': "BrokerTk",   # the Tk based GUI interface now used on windows
    }
else:
    confdefaults["EXTENSION_MODS"] = {}  # A list of extension mods.



### Exceptions:
class DictFileException(StandardError): pass
class ConfManagerException(StandardError): pass

### Functions:
def lines_to_dict(lines):
    '''Parses lines into a dict.'''
    dict = {}
    last = 0
    while last < len(lines):
        line = lines[last]
        first = lines.index(line) + 1
        last = first

        key, value = string.split(line, ':', 1)
        key = string.strip(key)
        value = string.strip(value)
        if dict.has_key(key):
            raise DictFileException, "Duplicate key %s." % key
        if value:
            # A typical string value:
            dict[key] = value
        else:
            # A "recursive dict" value:
            indent = string.find(line, string.lstrip(line))
            while (last < len(lines)) and (string.find(lines[last], string.lstrip(lines[last])) > indent):
                last = last + 1
            dict[key] = lines_to_dict(lines[first:last])
    return dict

def dict_to_lines(dict):
    '''Flatten a dict into human-readable lines.  (Sorts each same-depth tier lexographically.)'''
    lines = []
    keys = dict.keys()
    keys.sort()
    for key in keys:
        if type(dict[key]) == types.DictType:
            lines.append(str(key) + ":\n")
            lines = lines + map(lambda l: "\t" + l, dict_to_lines(dict[key]))
        else:
            lines.append("%s: %s\n" % (str(key), str(dict[key])))
    return lines

### Classes:
class ConfManager(UserDict.UserDict):
    '''Provides an interface to a configuration file.'''
    def __init__(self, defaults=confdefaults):
        '''defaults = A dict of default values.'''
        UserDict.UserDict.__init__(self)
        self.dict = self.data
        self.update(copy.deepcopy(defaults)) # Copy defaults, don't alter them!
        self._transient = false

    def set_transient(self):
        """
        After this is called, no changes can be made to the persistent broker.conf file, although
        changes can be made to the in-memory ConfMan instance.
        """
        self._transient = true

    def load(self):
        '''Parses a file into a dict.'''
        self.touch()
        file = open(os.path.expandvars(self.dict["PATH"]["BROKER_CONF"]))
        filedict = lines_to_dict(file.readlines())
        dictutil.recursive_dict_update(self.dict, filedict)
        file.close()
        if VersionNumber(self.dict.get("EGTP_VERSION_STR")) != VersionNumber(EGTP_VERSION_STR):
            mojolog.write("NOTE: Loading '%s' version config file while running '%s' version confutils\n" % (self.dict.get("EGTP_VERSION_STR"), EGTP_VERSION_STR))

        if platform == 'win32': 
            confdefaults['TCP_MAX_CONNECTIONS'] = 50
            if int(self.dict['TCP_MAX_CONNECTIONS']) > 50:
                mojolog.write('WARNING: TCP_MAX_CONNECTIONS lowered to a max of 50 on windows\n', vs='config')
                self.dict['TCP_MAX_CONNECTIONS'] = str(50)
            confdefaults['TCP_MAINTAINED_CONNECTIONS'] = 20
            if int(self.dict['TCP_MAINTAINED_CONNECTIONS']) > 20:
                mojolog.write('WARNING: TCP_MAINTAINED_CONNECTIONS lowered to a max of 20 on windows\n', vs='config')
                self.dict['TCP_MAINTAINED_CONNECTIONS'] = str(20)

        # upgrade older brokers to most recent dispersal defaults
        pub_new_default_date = self.dict['PUBLICATION'].get('CHANGED_TO_NEW_DEFAULT', '')
        if pub_new_default_date < '2001-08-15':
            self.dict['PUBLICATION']['CHANGED_TO_NEW_DEFAULT'] = iso_utc_time()[:10]
            self.dict['PUBLICATION']['SHARES_NEEDED'] = 12
            self.dict['PUBLICATION']['SHARES_GENERATED'] = 24

        # upgrade from old default to new
        if int(self.dict['TCP_CONNECT_TIMEOUT']) == 15:
            self.dict['TCP_CONNECT_TIMEOUT'] = 30

        # note for hackers
        self.dict['DEBUG_MODE'] = "please set operating system env var 'EVILDEBUG' or change MojoConstants.py instead of using this variable"
        # The reason for this is that there are some inner loops that get defined to behave more or less debuggishly at module load time.  If you use this runtime variable, the runtime and load time "debug" flags could be different, causing confusion.
        return

    def save(self):
        '''Writes dict to file.'''
        if self._transient:
            mojolog.write("ConfMan: NOT saving due to transience.\n")
            return

        self.dict["EGTP_VERSION_STR"] = EGTP_VERSION_STR
        mojolog.write('saving conf file %s (%s); PATH section:\n%s\n', args=(self.dict["PATH"]["BROKER_CONF"], os.path.expandvars(self.dict["PATH"]["BROKER_CONF"]), self.dict["PATH"],), v=6, vs='conf')
        file = open(os.path.expandvars(self.dict["PATH"]["BROKER_CONF"]), 'w')
        file.writelines(dict_to_lines(self.dict))
        file.flush()
        file.close()
        return

    def touch(self):
        '''Makes sure all named paths in self.dict["PATH"] exist.'''
        for key in self.dict["PATH"].keys():
            #isdir = key[-len("_DIR"):] == "_DIR"
            if key[-len("_DIR"):] == "_DIR":
                notdir = ""
            else:
                notdir = "not "
            # Treat notdir as a boolean.

            path = os.path.expandvars(self.dict["PATH"][key])
            #print "Touching %s which is %sa directory." % (path, notdir)

            if os.path.exists(path):
                continue

            # Create directories:
            if notdir:
                fileutil.make_dirs(os.path.dirname(path))
                # "Touch" the file:
                # PLATFORM NOTE: Make sure mode 'a' creates non-existent files and
                # does not truncate existing ones.
                open(path, 'a').close()
            else:
                fileutil.make_dirs(path)
        return

    def prune_empties(self, keys, strict=false):
        dictutil.prune_empties(self, keys)

    def del_keys(self, keys, strict=false):
        """
        example:

        self.del_keys( ('Key_X', 'Key_Y', 'Key_Z',) )

        -is equivalent to:

        if self.get('Key_X', {}).get('Key_Y', {}).has_key('Key_Z'):
            del self['Key_X']['Key_Y']['Key_Z']

        If `strict' then it raises an exception if the item identified by `keys' doesn't exist.
        """
        assert len(keys) >= 1, "one or more config file keys must be given"

        thing = self
        try:
            for key in keys[:-1]:
                thing = thing[key]

            del thing[keys[-1]]

            self.prune_empties(keys[:-1], self)
        except KeyError, e:
            if strict:
                raise

    def get_keys(self, keys, default=None, strict=false):
        """
        self.get_keys is a shortcut function that prevents an exception being raised,
        and instead returns a default in the case that any member wasn't found.

        For example:
        val = self.get_keys( ('Key_X', 'Key_Y', 'Key_Z'), 'Default_Value')
        -is equivalent to:
        val = self.get('Key_X', {}).get('Key_Y', {}).get('Key_Z', 'Default_Value')

        If strict is true instead of returning a default, an exception is raised.
        """
        assert len(keys) >= 1, "one or more config file keys must be given"
        thing = self
        try:
            for key in keys:
                thing = thing[key]
        except KeyError, e:
            if strict:
                raise
            else:
                return default
        return thing
    
    def set_keys(self, keys, value='true'):
        """
        The complement to get_keys.

        If the object represented by keys[:-1] is not a dict, an exception is raised.
        Else, that dict is assigned keys[-1] == value.
        """
        assert (type(keys) in (types.ListType, types.TupleType)) and (len(keys) >= 1), "one or more config file keys must be given in a tuple or list"
        if len(keys) > 1:
            d = self.get_keys(keys[:-1], strict=true)
        else:
            d = self.dict

        if type(d) != types.DictType:
            raise ConfManagerException, "Keys %s does not refer to a dictionary value.  type(self.get_keys(keys[:-1])) == %s" % (str(keys), str(type(d)))
        d[keys[-1]] = value
        
    def create_keys(self, keys, value='true', overwrite=false):
        """
        create_keys is much like set keys, except it will not
        raise an exception, instead it will ensure that the
        dict tree structure matches the format given by keys.

        if overwrite is true, the value will be set regardless.
        if it is false, the value is only set if there is not a currently
        initiated value.

        It returns the value found.  (If overwrite is true the return
        value will always be value.)
        """
        assert (type(keys) in (types.ListType, types.TupleType)) and (len(keys) >= 1), "one or more config file keys must be given in a tuple or list"
        d = self.dict
        keys, lastkey = list(keys[:-1]), keys[-1]

        while len(keys) > 0:
            key = keys.pop(0)
            if not d.has_key(key):
                d[key] = {}
            d = d[key]
        if overwrite or not d.has_key(lastkey):
            d[lastkey] = value
        return d[lastkey]
        
    def getlist(self, keys, default=None):
        """
        Loads self.get_keys([key0,key1,...,keyN]) as a list and returns the list.  This makes the underlying list
        encoding in the config file transparent to the application.

        -If default is None, then if a key is missing anywhere in the path specified, [] is returned, else default is
        returned.
        """
        if default is None:
            default = {}
        return dictToList(self.get_keys(keys, default=default))

    def getpath(self, keys, default=None):
        try:
            return os.path.expandvars(self.get_keys(keys, default=default))
        except TypeError:
            return default

    def setlist(self, keys, l):
        assert type(l) in (types.ListType, types.TupleType), "l must be a list or tuple, not a %s." % str(type(l))
        self.set_keys(keys, listToDict(l))
        
    def is_true_bool(self, keys, default="no", strict=false):
        """
        If the config value seems like a positive boolean string, return true,
        else return false.
        """
        return string.lower(self.get_keys(keys, default, strict)) in ('y', 'yes', 'true')

    def _onetime_collapse_path_vars(self):
        """
        A oneshot function meant to remove the old 'PATHS' section of the config file
        """
        mojolog.write("*** in onetime, PATH dict: %s\n", args=(self.dict.get('PATH'),), vs='conf', v=6)
        mojolog.write("*** in onetime, PATHS dict: %s\n", args=(self.dict.get('PATHS'),), vs='conf', v=6)
        if self.dict.has_key("PATHS"):
            mojolog.write("*** Converting `PATHS' section of conf file into new `PATH' section\n", vs='conf', v=0)
            evildir = os.environ.get('EVILDIR', '')
            evilconfdir = os.environ.get('EVILCONFDIR', '')
            home = os.environ.get('HOME', '')

            # a list of tuples of thing to replace with what to
            # replace it with.  this defines the order that the
            # replacements will be done in.  (since HOME is often a
            # part of the first two, it should be done last)
            replacements = [(evildir, '${EVILDIR}'), (evilconfdir, '${EVILCONFDIR}'), (home, '${HOME}')]

            for key, value in self.dict["PATHS"].items():
                for prefix, replacement in replacements:
                    mojolog.write('prefix: %s', args=(prefix,), v=6, vs='conf')
                    prefix = os.path.normpath(prefix) # This removes trailing separators...
                    mojolog.write('normpath(prefix): %s', args=(prefix,), v=6, vs='conf')
                    if prefix and value[:len(prefix)] == prefix:
                        mojolog.write("*** replacing %s in %s with %s\n", args=(prefix, value, replacement), vs='conf', v=0)
                        value = replacement + value[len(prefix):]
                        break
                self.dict["PATHS"][key] = value

            # store these under PATH and nuke the old (pre 2000-09-22) PATHS section
            self.dict["PATH"] = self.dict["PATHS"]
            del self.dict["PATHS"]

    def __nonzero__(self):
        return len(self.dict) != 0

# Create a ConfManager.  This is the only instance
# that should be used per run-time.
confman = ConfManager()
confman.load()
confman.save()  # This ensures the config file has the files the very first time the user runs anything.

try:
    vs = dictToList(confman["LOG_VS"])
except:
    pass
else:
    mojolog.reset_log_vs(vs)
    
### Tests and Testing:
def test__lines_to_dict__AGAINST__dict_to_lines__A():
    a =["I:\n",
        "\tA: IA\n",
        "\tB: IB\n",
        "\tC:\n",
        "\t\t1:\n",
        "\t\t\ta: IC1a\n",
        "\t\t2: IC2\n",
        "\tD: ID\n",
        "II: II\n",
        "III: III\n"]
    b = dict_to_lines(lines_to_dict(a))
    assert len(a) == len(b), "There were %d input lines, but %d output lines." % (len(a),len(b))
    for i in range(0, len(a)):
        assert a[i] == b[i], "%s != %s" % (`a[i]`, `b[i]`)
    return

def test_hmac():
    def longtobytes(n,block=1): #Slow!
        r = ""
        while n>0:
            r = chr(n&0xff) + r
            n = n >> 8
        if len(r)% block:
            r = chr(0)*(block-len(r)%block) + r
        return r
    test_vectors_sha = [
        #(key,data,result)
        #Taken from rfc2202
        ("\x0b"*20,"Hi There",0xb617318655057264e28bc0b6fb378c8ef146be00L),
        ("Jefe","what do ya want for nothing?",0xeffcdf6ae5eb2fa2d27416d5f184df9c259a7c79L),
        ("\xAA"*20,"\xDD"*50,0x125d7342b9ac11cd91a39af48aa17b4f63f175d3L),
        (0x0102030405060708090a0b0c0d0e0f10111213141516171819L,"\xcd"*50,
         0x4c9007f4026250c6bc8414f9bf50c86c2d7235daL),
        ("\x0c"*20,"Test With Truncation",0x4c1a03424b55e07fe7f27be1d58bb9324a9a5a04L),
        ("\xaa"*80,"Test Using Larger Than Block-Size Key - Hash Key First",
         0xaa4ae5e15272d00e95705637ce8a3b55ed402112L),
        ("\xaa"*80,
         "Test Using Larger Than Block-Size Key and Larger Than One Block-Size Data",
         0xe8e99d0f45237d786d6bbaa7965c7808bbff1a91L),
        ]
    for (key,data,result) in test_vectors_sha:
        if type(key)==type(1L): key=longtobytes(key)
        if type(data)==type(1L): data=longtobytes(data)
        if type(result)==type(1L): result=longtobytes(result,20)
        assert hmac(key,data) == result, "Failed on %s" % repr((key,data,result))

def run(argv):
    if len(argv) > 1:
        if argv[1] == "test":
            do_tests()
        elif argv[1] == "dump":
            sys.stdout.writelines(dict_to_lines(confman.dict))
        else:
            print 'Unknown option "%s".' % argv[1]
    else:
        print 'Config file "%s" updated.' % confman["PATH"]["BROKER_CONF"]

if __name__ == '__main__':
    run(sys.argv)

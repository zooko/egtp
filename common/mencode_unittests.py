#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: mencode_unittests.py,v 1.1 2002/06/25 03:54:57 zooko Exp $'


# Python standard library modules
import operator
import random
import traceback

try:
    import unittest
except:
    class unittest:
        class TestCase:
            pass
        pass
    pass

# pyutil modules
import humanreadable
import memutil

# Mnet modules
from mencode import *

class Testy(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_decode_random_illformed_junk(self):
        try:
            mdecode(string.join(filter(lambda x: x != ':', map(chr, map(random.randrange, [0]*20, [256]*20))), ''))
            raise "This shouldn't have decoded without an exception."
        except MencodeError:
            # Good.  That was definitely ill-formed.
            pass

    def test_decode_other_random_illformed_junk(self):
        l = random.randrange(0, 200)
        s = str(l) + ':' + "x" * (l-1) # too short.  Heh heh.
        try:
            mdecode(s)
            raise "This shouldn't have decoded without an exception."
        except MencodeError:
            # Good.  That was definitely ill-formed.
            pass

    def test_decode_unknown(self):
        try:
            decode_unknown('(())', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        try:
            decode_unknown('((111))', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        assert decode_unknown('((0:))', 0) == (UNKNOWN_TYPE, 5)
        assert decode_unknown(')', 0) == (UNKNOWN_TYPE, 0)
        assert decode_unknown('1:a2:ab)', 0) == (UNKNOWN_TYPE, 7)

    def test_encode_and_decode_string_with_nulls(self):
        strwn = "\000\001\000"

    def test_encode_and_decode_none(self):
        assert mdecode(mencode(None)) == None

    def test_encode_and_decode_long(self):
        assert mdecode(mencode(-23452422452342L)) == -23452422452342L

    def test_encode_and_decode_int(self):
        assert mdecode(mencode(2)) == 2

    def test_dict_enforces_order(self):
        mdecode('(4:dict(3:int1:0)(4:null)(3:int1:1)(4:null))')
        try:
            mdecode('(4:dict(3:int1:1)(4:null)(3:int1:0)(4:null))')
        except MencodeError:
            pass

    def test_dict_forbids_key_repeat(self):
        try:
            mdecode('(4:dict(3:int1:1)(4:null)(3:int1:1)(4:null))')
        except MencodeError:
            pass

    def test_decode_unknown_type_not_in_dict(self):
        try:
            mdecode('(7:garbage)')
            return false
        except UnknownTypeError:
            pass

    def test_decode_unknown_type_in_dict(self):
        # I strongly disagree with this feature.  It violates canonicity (which, as we all know, open up security holes), as well as being potentially confusing to debuggers and to mencode maintainers, and it is currently not needed.  --Zooko 2001-06-03
        assert mdecode('(4:dict(7:garbage)(3:int1:4)(4:null)(3:int1:5))') == {None: 5}
        assert mdecode('(4:dict(4:null)(3:int1:5)(3:int1:4)(7:garbage))') == {None: 5}

    def test_MencodeError_in_decode_unknown(self):
        try:
            mdecode('(4:dict(7:garbage)(2:int1:4)(4:null)(3:int1:5))')
            return 0
        except MencodeError:
            pass

    def test_decode_raw_string(self):
        assert decode_raw_string('1:a', 0) == ('a', 3)
        assert decode_raw_string('0:', 0) == ('', 2)
        assert decode_raw_string('10:aaaaaaaaaaaaaaaaaaaaaaaaa', 0) == ('aaaaaaaaaa', 13)
        assert decode_raw_string('10:', 1) == ('', 3)
        try:
            decode_raw_string('11:', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        try:
            decode_raw_string('01:a', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        try:
            decode_raw_string('11', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        try:
            decode_raw_string('h', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass
        try:
            decode_raw_string('h:', 0)
            return 0
        except IndexError:
            pass
        except ValueError:
            pass
        except MencodeError:
            pass

    def test_decode_noncanonical_int(self):
        try:
            mdecode('(3:int2:03)')
            assert false, "non canonical integer allowed '03'"
        except MencodeError:
            pass
        try:
            mdecode('(3:int2:3 )')
            assert false, "non canonical integer allowed '3 '"
        except MencodeError:
            pass
        try:
            mdecode('(3:int2: 3)')
            assert false, "non canonical integer allowed ' 3'"
        except MencodeError:
            pass
        try:
            mdecode('(3:int2:-0)')
            assert false, "non canonical integer allowed '-0'"
        except MencodeError:
            pass

    def test_encode_and_decode_hash_key(self):
        x = {42: 3}
        y = {'42': 3}
        assert mdecode(mencode(x)) == x
        assert mdecode(mencode(y)) == y

    def test_encode_and_decode_list(self):
        assert mdecode(mencode([])) == []

    def test_encode_and_decode_tuple(self):
        assert mdecode(mencode(())) == []

    def test_encode_and_decode_dict(self):
        assert mdecode(mencode({})) == {}

    def test_encode_and_decode_complex_object(self):
        spam = [[], 0, -3, -345234523543245234523L, {}, 'spam', None, {'a': 3}, {69: []}]
        assert mencode(mdecode(mencode(spam))) == mencode(spam)
        assert mdecode(mencode(spam)) == spam

    def test_preencoded_thing(self):
        thing = {"dirty limmerk": ["there once was a man from peru", "who set out to sail a canoe"]}
        pthing = PreEncodedThing(thing)
        assert len(mencode(thing)) == len(pthing)
        assert mencode(pthing) == mencode(thing)
        assert mdecode(mencode(thing)) == mdecode(mencode(pthing))

    def test_dict_as_key(self):
        try:
            mdecode('(4:dict(4:dict)(4:null))')
            assert false, "dict cannot be a key but it was allowed by mdecode"
        except MencodeError:
            return

    def test_rej_dict_with_float(self):
        try:
            s = mencode({'foo': 0.9873})
            assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % humanreadable.hr(s)
        except MencodeError, le:
            try:
                # print "got exce1: %s" % humanreadable.hr(le)
                s2 = mencode({'foo': 0.9873})
                assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % humanreadable.hr(s2)
            except MencodeError, le:
                # print "got exce2: %s" % humanreadable.hr(le)
                # Good!  we want an exception when we try this.
                return

    def test_rej_float(self):
        try:
            s = mencode(0.9873)
            assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % humanreadable.hr(s)
        except MencodeError, le:
            try:
                s2 = mencode(0.9873)
                assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % humanreadable.hr(s2)
            except MencodeError, le:
                # Good!  we want an exception when we try this.
                return

    def test_no_leakage(self):
        # Test every (other) test here for leakage!  That's my cheap way to try to exercise the weird internal cases in the compiled code...
        for m in dir(self.__class__):
            if m[:len("test_")] == "test_":
                if m != "test_no_leakage":
                    # print "testing for memory leak: %s" % m
                    self._help_test_no_leakage(getattr(self, m))

    def _help_test_no_leakage(self, f):
        slope = memutil.measure_mem_leakage(f, 2**7, iterspersample=2**4)

        # print "slope: ", slope
        if slope > 0.0001:
            raise "%s leaks memory at a rate of approximately %s Python objects per invocation" % (f, slope,)

def _bench_it_mencode(n):
    """
    For use with utilscripts/benchfunc.py.
    """
    d = {}
    for i in xrange(n):
        d[i] = { i: 'spam', i + 1: 'eggs', i * 2: 'bacon'}

    mencode(d)

def _bench_it_mencode_plus_mdecode(n):
    """
    For use with utilscripts/benchfunc.py.
    """
    d = {}
    for i in xrange(n):
        d[i] = { i: 'spam', i + 1: 'eggs', i * 2: 'bacon'*n}

    mdecode(mencode(d))

def _profile_test_mdecode_implementation_speed():
    import mojoutil
    profit = mojoutil._dont_enable_if_you_want_speed_profit
    profit(_real_test_mdecode_implementation_speed)

def _real_test_mdecode_implementation_speed():
    import os
    import time
    msgpath = os.path.join(os.environ.get('HOME'), 'tmp/messages')
    filenamelist = os.listdir(msgpath)
    filenamelist.sort()
    encoded_messages = []
    sizes_list = []
    for name in filenamelist:
        encoded_messages.append( open(os.path.join(msgpath, name), 'rb').read() )
        sizes_list.append( len(encoded_messages[-1]) )
    totalbytes = reduce(lambda a,b: a+b, sizes_list)
    average = totalbytes / len(sizes_list)
    sizes_list.sort()
    median = sizes_list[len(sizes_list)/2]
    print 'read in %d messages totaling %d bytes, averaging %d bytes, median size of %d' % (len(sizes_list), totalbytes, average, median)

    ### 100% python speed test
    print 'decoding using python implementation...'

    # setup
    decodersdict['string'] = decode_raw_string
    # end setup

    t1 = time.time()
    for m in encoded_messages:
        try:
            mdecode(m)
        except:
            print '!',
    t2 = time.time()
    print 'done.  total decoding time: %3.3f' % (t2 - t1,)

    ### partial C speed test
    print 'decoding using partial C implementation...'

    # setup
    decode_raw_string = _c_mencode_help._c_decode_raw_string
    decodersdict['string'] = decode_raw_string
    # end setup

    t1 = time.time()
    for m in encoded_messages:
        try:
            mdecode(m)
        except:
            print '!',
    t2 = time.time()
    print 'done.  total decoding time: %3.3f' % (t2 - t1,)

def _profile_test_mencode_implementation_speed():
    import mojoutil
    profit = mojoutil._dont_enable_if_you_want_speed_profit
    profit(_real_test_mencode_implementation_speed)

def _real_test_mencode_implementation_speed():
    import os
    import time
    msgpath = os.path.join(os.environ.get('HOME'), 'tmp/messages')
    filenamelist = os.listdir(msgpath)
    filenamelist.sort()
    decoded_messages = []
    sizes_list = []
    for name in filenamelist:
        encoding = open(os.path.join(msgpath, name), 'rb').read()
        sizes_list.append( len(encoding) )
        decoded_messages.append( mdecode(encoding) )
    totalbytes = reduce(lambda a,b: a+b, sizes_list)
    average = totalbytes / len(sizes_list)
    sizes_list.sort()
    median = sizes_list[len(sizes_list)/2]
    print 'read and decoded %d messages totaling %d bytes, averaging %d bytes, median size of %d' % (len(sizes_list), totalbytes, average, median)

    ### 100% python speed test
    print 'encoding using python implementation...'

    # setup
    # TODO none needed yet
    # end setup

    t1 = time.time()
    for m in decoded_messages:
        try:
            mencode(m)
        except:
            print '!',
    t2 = time.time()
    print 'done.  total encoding time: %3.3f' % (t2 - t1,)


def _real_test_encode_string_implementation_speed():
    import os, time
    ntests = 500
    mlog = os.path.join(os.environ.get('MNETDIR'), 'common', 'mencode.py')
    lines = open(mlog, 'r').readlines()
    del(mlog)
    o = StringIO()
    t1 = time.time()
    for i in xrange(ntests):
        for line in lines:
            encode_string(line, o)
        o.seek(0)
    t2 = time.time()
    print 'done testing python impl of encode_string.  total encoding time: %3.3f' % (t2 - t1,)

    _c_encode_string = _c_mencode_help._c_encode_string
    o = StringIO()
    t1 = time.time()
    for i in xrange(ntests):
        for line in lines:
            _c_encode_string(line, o)
        o.seek(0)
    t2 = time.time()
    print 'done testing C impl of encode_string.  total encoding time: %3.3f' % (t2 - t1,)

if __name__ == '__main__':
    if hasattr(unittest, 'main'):
        unittest.main()
    else:
        # Here's our manual implementation of unittest:
        t = Testy()
        for m in dir(t.__class__):
            if m[:len("test_")] == "test_":
                print m, "... ",
                getattr(t, m)()
                print
        pass

#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

true = 1
false = 0

### standard modules
import types
import string
from cStringIO import StringIO
import re
# try:
#     from c_mencode import _c_mencode_help    
#     _use_c_mencode = true
# except ImportError:
#     print 'NOTE: c_mencode not found, using 100% python implementation of mencode'
#     _use_c_mencode = false
_use_c_mencode = false

# for speed, its used in the most called function
_find = string.find

### our modules
import std


__doc__ = """
Methods to be used from other modules are mencode and mdecode
"""

class PreEncodedThing:
    """
    This class is used by servers who are attempting to lighten
    their load by memoizing encoding of some common parts of their
    response.
    'It was written during the meta tracker load crunch of 8-Oct-2000'
    """
    def __init__(self, thing):
        self.__thing = mencode(thing)
    def getvalue(self):
        return self.__thing
    def __len__(self):
        return len(self.__thing)

if _use_c_mencode:
    # use the dictionary that the C code created and has a reference to
    encodersdict = _c_mencode_help._c_encoder_dict
else:
    encodersdict = {}

    
def encode_int(data, result):
    #assert type(data) is types.IntType
    enc = str(data)
    result.write('(3:int')
    result.write(str(len(enc)))
    result.write(':')
    result.write(enc)
    result.write(')')

encodersdict[types.IntType] = encode_int

def encode_long(data, result):
    #assert type(data) is types.LongType
    enc = str(data)
    # remove the ending 'L' that python 1.5.2 adds
    if enc[-1] == 'L':
        enc = enc[:-1]
    result.write('(3:int')
    result.write(str(len(enc)))
    result.write(':')
    result.write(enc)
    result.write(')')

encodersdict[types.LongType] = encode_long

def encode_list(data, result):
    #assert type(data) is types.TupleType or type(data) is types.ListType
    result.write('(4:list')
    for i in data:
        encode_io(i, result)
    result.write(')')

encodersdict[types.TupleType] = encode_list
encodersdict[types.ListType] = encode_list

def _py_encode_string(data, result):
    #assert type(data) is types.StringType
    result.write('(6:string')
    result.write(str(len(data)))
    result.write(':')
    result.write(str(data))
    result.write(')')

if _use_c_mencode:
    encode_string = _c_mencode_help._c_encode_string
else:
    encode_string = _py_encode_string

encodersdict[types.StringType] = encode_string
encodersdict[types.BufferType] = encode_string
    
def _py_encode_dict(data, result):
    #assert type(data) is types.DictType
    result.write('(4:dict')
    keys = data.keys()
    # TODO use an mencode specific comparison function here.
    # Strings must be greater than numbers.  The python language doesn't actually guarantee this.
    keys.sort()
    for key in keys:
        if type(key) not in (types.StringType, types.BufferType, types.IntType, types.LongType):
            raise MencodeError, 'mencoded dictionary keys must be strings or numbers: %s :: %s' % (std.hr(key), std.hr(type(key)),)
        encode_io(key, result)
        encode_io(data[key], result)
    result.write(')')
if _use_c_mencode:
    encode_dict = _c_mencode_help._c_encode_dict
else:
    encode_dict = _py_encode_dict

encodersdict[types.DictType] = encode_dict
    
def encode_none(data, result):
    #assert data is None
    result.write('(4:null)')

encodersdict[types.NoneType] = encode_none

def encode_preencoded(data, result):
    assert isinstance(data, PreEncodedThing), "the only class that can be mencoded are PreEncodedThing classes"
    result.write(data.getvalue())

encodersdict[types.InstanceType] = encode_preencoded

def _py_encode_io(data, result):
    encoder = encodersdict.get(type(data))
    if not encoder:
        raise MencodeError, 'unsupported data type: %s :: %s' % (std.hr(data), std.hr(type(data)),)
    encoder(data, result)

if _use_c_mencode:
    encode_io = _c_mencode_help._c_encode_io
else:
    encode_io = _py_encode_io
    
def mencode(data):
    """
    Takes a nested Python data structure, including possibly lists, tuples, ints, longs,
    dicts, strings, and None, and encodes it as an sexp.
    
    lists and tuples are encoded the same way, as are ints and longs.
    
    The only nesting structure not allowed is that lists and dicts are not allowed to 
    be keys in a dict - they aren't hashable.
    """
    result = StringIO()
    try:
        encode_io(data, result)
    except ValueError, le:
        # The ValueError results from memory exhaustion.  Memory exhaustion should be handled higher up (ultimately by aborting the current transaction, I think.)  --Zooko 2001-08-27
        raise MemoryError, le
    except MencodeError, le:
        raise MencodeError, "Couldn't encode this data object: %s, le: %" % (std.hr(data), std.hr(le),)
    return result.getvalue()

if _use_c_mencode:
    MencodeError = _c_mencode_help._c_MencodeError
else:
    class MencodeError(StandardError): pass

# for backwards compatibility in case I missed changing anything - this shouldn't be necessary
Error = MencodeError

class UnknownTypeError(MencodeError): pass

def mdecode(s):
    """
    Does the opposite of mencode. Raises a mencode.MencodeError if the string is not a proper Python
    data structure encoding.

    @precondition `s' must be a string.: type(s) is types.StringType: "s: %s :: %s" % (std.hr(s), std.hr(type(s)),)
    """
    assert type(s) is types.StringType, "precondition: `s' must be a string." + " -- " + "s: %s :: %s" % (std.hr(s), std.hr(type(s)),)

    try:
        result, index = mdecode_index(s, 0)
        if index != len(s):
            raise MencodeError, 'garbage at end of s'
        if result == UNKNOWN_TYPE:
            raise UnknownTypeError, 'unknown type in required part of message'
        return result
    except IndexError, e:
        raise MencodeError, 'unexpected end of s ' + std.hr(e)
    except ValueError, e:
        raise MencodeError, 'bad format ' + std.hr(e)
    except TypeError, e:
        raise MencodeError, 'type problem ' + std.hr(e)

global decodersdict
decodersdict = {}

def _py_decode_raw_string(s, index, _find=_find):
    index2 = _find(s, ':', index)
    if index2 == -1:
        raise MencodeError, 'unterminated string - no colon'
    l = int(s[index: index2])
    if l != 0 and s[index] == '0':
        raise MencodeError, "string lengths can't start with 0 unless they are 0"
    endindex = index2 + 1 + l
    if endindex > len(s):
        raise MencodeError, 'unexpected end of s'
    return s[index2 + 1: endindex], endindex

if _use_c_mencode:
    # this runs 25-50% faster than the python version
    global decode_raw_string 
    decode_raw_string = _c_mencode_help._c_decode_raw_string
else:
    global decode_raw_string 
    decode_raw_string = _py_decode_raw_string

global decodersdict
decodersdict['string'] = decode_raw_string

def test_decode_raw_string():
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

_int_re = re.compile(r'^(0|-?[1-9][0-9]*)$')
def decode_int(s, index):
    n, index = decode_raw_string(s, index)
    if not _int_re.match(n):
        raise MencodeError, "non canonical integer: %s" % std.hr(n)
    try:
        return int(n), index
    except (OverflowError, ValueError), le:
        return long(n), index

global decodersdict
decodersdict['int'] = decode_int

def decode_null(s, index):
    return None, index
    
global decodersdict
decodersdict['null'] = decode_null

def decode_list(s, index):
    result = []
    while s[index] != ')':
        next, index = mdecode_index(s, index)
        result.append(next)
    return result, index
    
global decodersdict
decodersdict['list'] = decode_list

def decode_dict(s, index):
    result = {}
    firstkey = true

    while s[index] != ')':
        try:
            key, index = mdecode_index(s, index)
        except MencodeError, le:
            raise MencodeError, ("Error decoding key at index: %d, le follows: " % index, le,)
        try:
            value, index = mdecode_index(s, index)
        except MencodeError, le:
            raise MencodeError, ("Error decoding value after key: %s, at index: %d, le follows: " % (str(key), index,), le,)
        if key == UNKNOWN_TYPE or value == UNKNOWN_TYPE:
            continue
        # Guarantee that dicts are stored with their keys in sorted order.  This is
        # needed to guarantee that mencoding things are always in canonical form.
        if firstkey:
            firstkey = false
        else:
            # TODO use an mencode specific comparison function here.
            # Strings must be greater than numbers.  The python language doesn't actually guarantee this.
            if key <= prevkey:
                raise MencodeError, "out of order keys in serialized dict: %s.  %s is not greater than %s\n" % (std.hr(s), std.hr(key), std.hr(prevkey),)
        prevkey = key
        result[key] = value
    return result, index

global decodersdict
decodersdict['dict'] = decode_dict

def test_dict_enforces_order():
    mdecode('(4:dict(3:int1:0)(4:null)(3:int1:1)(4:null))')
    try:
        mdecode('(4:dict(3:int1:1)(4:null)(3:int1:0)(4:null))')
    except MencodeError:
        pass
    
def test_dict_forbids_key_repeat():
    try:
        mdecode('(4:dict(3:int1:1)(4:null)(3:int1:1)(4:null))')
    except MencodeError:
        pass

def test_decode_unknown_type_not_in_dict():
    try:
        mdecode('(7:garbage)')
        return false
    except UnknownTypeError:
        pass
    
def test_decode_unknown_type_in_dict():
    # I strongly disagree with this feature.  It violates canonicity (which, as we all know, open up security holes), as well as being potentially confusing to debuggers and to mencode maintainers, and it is currently not needed.  --Zooko 2001-06-03
    assert mdecode('(4:dict(7:garbage)(3:int1:4)(4:null)(3:int1:5))') == {None: 5}
    assert mdecode('(4:dict(4:null)(3:int1:5)(3:int1:4)(7:garbage))') == {None: 5}

def test_MencodeError_in_decode_unknown():
    try:
        mdecode('(4:dict(7:garbage)(2:int1:4)(4:null)(3:int1:5))')
        return 0
    except MencodeError:
        pass

def UNKNOWN_TYPE():
    pass

def decode_unknown(s, index):
    depth = 0
    while true:
        while s[index] == ')':
            depth = depth - 1
            if depth <= 0:
                return UNKNOWN_TYPE, index
            index = index + 1
        while s[index] == '(':
            depth = depth + 1
            index = index + 1
        waste, index = decode_raw_string(s, index)

def test_decode_unknown():
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

def mdecode_index(s, index):
    """
    return object, new index
    """
    if s[index] != '(':
        raise MencodeError, "Object encodings must begin with an open parentheses.  index: %d, s: %s" % (index, std.hr(s),)
    next_type, index = decode_raw_string(s, index + 1)
    global decodersdict
    decoder = decodersdict.get(next_type, decode_unknown)
    result, index = decoder(s, index)
    if s[index] != ')':
        raise MencodeError, "Object encodings must end with a close parentheses.  index: %d, s: %s" % (index, std.hr(s),)
    return result, index + 1


def test_encode_and_decode_string_with_nulls():
    strwn = "\000\001\000"
    

def test_encode_and_decode_none():
    assert mdecode(mencode(None)) == None
    
def test_encode_and_decode_long():
    assert mdecode(mencode(-23452422452342L)) == -23452422452342L

def test_encode_and_decode_int():
    assert mdecode(mencode(2)) == 2

def test_decode_noncanonical_int():
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

def test_encode_and_decode_hash_key():
    x = {42: 3}
    y = {'42': 3}
    assert mdecode(mencode(x)) == x
    assert mdecode(mencode(y)) == y

def test_encode_and_decode_list():
    assert mdecode(mencode([])) == []

def test_encode_and_decode_tuple():
    assert mdecode(mencode(())) == []

def test_encode_and_decode_dict():
    assert mdecode(mencode({})) == {}

def test_encode_and_decode_complex_object():
    spam = [[], 0, -3, -345234523543245234523L, {}, 'spam', None, {'a': 3}, {69: []}]
    assert mencode(mdecode(mencode(spam))) == mencode(spam)
    assert mdecode(mencode(spam)) == spam

def test_preencoded_thing():
    thing = {"dirty limmerk": ["there once was a man from peru", "who set out to sail a canoe"]}
    pthing = PreEncodedThing(thing)
    assert len(mencode(thing)) == len(pthing)
    assert mencode(pthing) == mencode(thing)
    assert mdecode(mencode(thing)) == mdecode(mencode(pthing))

def test_dict_as_key():
    try:
        mdecode('(4:dict(4:dict)(4:null))')
        assert false, "dict cannot be a key but it was allowed by mdecode"
    except MencodeError:
        return

# import traceback
def test_rej_dict_with_float():
    try:
        s = mencode({'foo': 0.9873})
        assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % std.hr(s)
    except MencodeError, le:
        try:
            # print "got exce1: %s" % std.hr(le)
            # traceback.print_exc()
            s2 = mencode({'foo': 0.9873})
            assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % std.hr(s2)
        except MencodeError, le:
            # print "got exce2: %s" % std.hr(le)
            # traceback.print_exc()
            # Good!  we want an exception when we try this.
            return

def test_rej_float():
    try:
        s = mencode(0.9873)
        assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % std.hr(s)
    except MencodeError, le:
        try:
            s2 = mencode(0.9873)
            assert 0, "You can't encode floats!  Anyway, the result: %s, is probably not what we meant." % std.hr(s2)
        except MencodeError, le:
            # Good!  we want an exception when we try this.
            return

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
    global decode_raw_string, decodersdict
    decode_raw_string = _py_decode_raw_string
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
    global decode_raw_string, decodersdict
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
    mlog = os.path.join(os.environ.get('EVILDIR'), 'common', 'mencode.py')
    lines = open(mlog, 'r').readlines()
    del(mlog)
    o = StringIO()
    t1 = time.time()
    for i in xrange(ntests):
        for line in lines:
            _py_encode_string(line, o)
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

def runalltests():
    import RunTests
    RunTests.runTests('mencode')

mojo_test_flag = 1
if __name__ == '__main__':
    runalltests()


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: mencode.py,v 1.2 2002/06/25 03:42:27 zooko Exp $'

# Python standard library modules
from cStringIO import StringIO
import re
import string
import types

true = 1
false = 0

# pyutil modules
import humanreadable

# Mnet modules

# Try importing faster compiled versions of these functions and objects.
c_encodersdict = None
c_encode_string = None
c_encode_dict = None
c_encode_io = None
c_MencodeError = None
c_decode_raw_string = None
try:
#     # Disabling the C-accelerated version for now, as it leaks memory.
#     raise "Disabling the C-accelerated version for now, as it leaks memory."

    from c_mencode import _c_mencode_help    
    c_encodersdict = _c_mencode_help._c_encoder_dict
    c_encode_string = _c_mencode_help._c_encode_string
    c_encode_dict = _c_mencode_help._c_encode_dict
    c_encode_io = _c_mencode_help._c_encode_io
    c_MencodeError = _c_mencode_help._c_MencodeError
    c_decode_raw_string = _c_mencode_help._c_decode_raw_string
    _use_c_mencode = true
    print 'NOTE: c_mencode found, using accelerated C version of mencode'
except:
    _use_c_mencode = false
    print 'NOTE: c_mencode not found, using 100% python implementation of mencode'
# Now at the end of this file, we'll overwrite the Python functions and objects with the compiled functions and objects if they are not `None'.

# for speed, its used in the most called function
_find = string.find


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

def encode_int(data, result):
    #assert type(data) is types.IntType
    enc = str(data)
    result.write('(3:int')
    result.write(str(len(enc)))
    result.write(':')
    result.write(enc)
    result.write(')')

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

def encode_list(data, result):
    #assert type(data) is types.TupleType or type(data) is types.ListType
    result.write('(4:list')
    for i in data:
        encode_io(i, result)
    result.write(')')

def encode_string(data, result):
    #assert type(data) is types.StringType
    result.write('(6:string')
    result.write(str(len(data)))
    result.write(':')
    result.write(str(data))
    result.write(')')

def encode_dict(data, result):
    #assert type(data) is types.DictType
    result.write('(4:dict')
    keys = data.keys()
    # TODO use an mencode specific comparison function here.
    # Strings must be greater than numbers.  The python language doesn't actually guarantee this.
    keys.sort()
    for key in keys:
        if type(key) not in (types.StringType, types.BufferType, types.IntType, types.LongType):
            raise MencodeError, 'mencoded dictionary keys must be strings or numbers: %s :: %s' % (humanreadable.hr(key), humanreadable.hr(type(key)),)
        encode_io(key, result)
        encode_io(data[key], result)
    result.write(')')
    
def encode_none(data, result):
    #assert data is None
    result.write('(4:null)')

def encode_preencoded(data, result):
    assert isinstance(data, PreEncodedThing), "the only class that can be mencoded are PreEncodedThing classes"
    result.write(data.getvalue())

def encode_io(data, result):
    encoder = encodersdict.get(type(data))
    if not encoder:
        raise MencodeError, 'unsupported data type: %s :: %s' % (humanreadable.hr(data), humanreadable.hr(type(data)),)
    encoder(data, result)

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
        raise MencodeError, "Couldn't encode this data object: %s, le: %s" % (humanreadable.hr(data), humanreadable.hr(le),)
    return result.getvalue()

def mdecode(s):
    """
    Does the opposite of mencode. Raises a mencode.MencodeError if the string is not a proper Python
    data structure encoding.

    @precondition `s' must be a string.: type(s) is types.StringType: "s: %s :: %s" % (humanreadable.hr(s), humanreadable.hr(type(s)),)
    """
    assert type(s) is types.StringType, "precondition: `s' must be a string." + " -- " + "s: %s :: %s" % (humanreadable.hr(s), humanreadable.hr(type(s)),)

    try:
        result, index = mdecode_index(s, 0)
        if index != len(s):
            raise MencodeError, 'garbage at end of s'
        if result == UNKNOWN_TYPE:
            raise UnknownTypeError, 'unknown type in required part of message'
        return result
    except IndexError, e:
        raise MencodeError, 'unexpected end of s ' + humanreadable.hr(e)
    except ValueError, e:
        raise MencodeError, 'bad format ' + humanreadable.hr(e)
    except TypeError, e:
        raise MencodeError, 'type problem ' + humanreadable.hr(e)

def decode_raw_string(s, index, _find=_find):
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

_int_re = re.compile(r'^(0|-?[1-9][0-9]*)$')
def decode_int(s, index):
    n, index = decode_raw_string(s, index)
    if not _int_re.match(n):
        raise MencodeError, "non canonical integer: %s" % humanreadable.hr(n)
    try:
        return int(n), index
    except (OverflowError, ValueError), le:
        return long(n), index

def decode_null(s, index):
    return None, index
    
def decode_list(s, index):
    result = []
    while s[index] != ')':
        next, index = mdecode_index(s, index)
        result.append(next)
    return result, index
    
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
                raise MencodeError, "out of order keys in serialized dict: %s.  %s is not greater than %s\n" % (humanreadable.hr(s), humanreadable.hr(key), humanreadable.hr(prevkey),)
        prevkey = key
        result[key] = value
    return result, index

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

def mdecode_index(s, index):
    """
    return object, new index
    """
    if s[index] != '(':
        raise MencodeError, "Object encodings must begin with an open parentheses.  index: %d, s: %s" % (index, humanreadable.hr(s),)
    next_type, index = decode_raw_string(s, index + 1)
    decoder = decodersdict.get(next_type, decode_unknown)
    result, index = decoder(s, index)
    if s[index] != ')':
        raise MencodeError, "Object encodings must end with a close parentheses.  index: %d, s: %s" % (index, humanreadable.hr(s),)
    return result, index + 1


class MencodeError(StandardError): pass
# for backwards compatibility in case I missed changing anything - this shouldn't be necessary
Error = MencodeError
class UnknownTypeError(MencodeError): pass

# Now we'll create the global data structures and overwrite anything that has a C accelerated version.
encodersdict = {}

if c_encodersdict is not None:
    encodersdict = c_encodersdict

if c_encode_string is not None:
    encode_string = c_encode_string
if c_encode_dict is not None:
    encode_dict = c_encode_dict
if c_encode_io is not None:
    encode_io = c_encode_io
if c_decode_raw_string is not None:
    decode_raw_string = c_decode_raw_string

if c_MencodeError is not None:
    MencodeError = c_MencodeError

decodersdict = {}

# C-accelerated version is implemented:
encodersdict[types.StringType] = encode_string
encodersdict[types.BufferType] = encode_string
encodersdict[types.DictType] = encode_dict
encodersdict[types.NoneType] = encode_none

decodersdict['string'] = decode_raw_string

# C-accelerated version is not implemented:
encodersdict[types.InstanceType] = encode_preencoded
encodersdict[types.IntType] = encode_int
encodersdict[types.LongType] = encode_long
encodersdict[types.TupleType] = encode_list
encodersdict[types.ListType] = encode_list

decodersdict['int'] = decode_int
decodersdict['null'] = decode_null
decodersdict['list'] = decode_list
decodersdict['dict'] = decode_dict


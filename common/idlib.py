#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# Common code for encoding and decoding Mojo Nation (TM) object IDs
# in their two common representations (binary and ascii/mojosixbit).
#
# Everything in this file is optimized for speed, it gets called a
# -lot- throughout the program, including many hot spots.
#
# $Id: idlib.py,v 1.1 2002/01/29 20:07:05 zooko Exp $

### standard modules
import re
import sha
import struct
import types

### our modules
import MojoConstants
import std
import mojosixbit
import randsource
import std

_asciihash_re = mojosixbit._asciihash_re

try:
    unicode
    _strtypes = (types.StringType, types.UnicodeType)
except:
    _strtypes = (types.StringType,)

Size_of_NativeId_Int_Space = 2**24
Largest_Distance_NativeId_Int_Space = 2**23

def sign(id1, id2):
    """
    @returns `1' if the distance in the increasing direction around the circle from `id1' to `id2' is shorter than the distance in the decreasing direction, else returns `-1';  If (in *native int* form) id1 == id2, or id1 == (id2+Largest_Distance_NativeId_Int_Space), then return 0.
    """
    id1 = id_to_native_int(id1)
    id2 = id_to_native_int(id2)
    if id1 == id2:
        return 0
    dist = distance(id1, id2)
    if dist == Largest_Distance_NativeId_Int_Space:
        return 0

    if id1 + dist == id2:
        return 1
    else:
        return -1

def distance(id1, id2):
    """
    @param id1 an id, can be in native-int form (for extra speed -- it converts them to native int anyway so it doesn't change the answer)
    @param id2 an id, can be in native-int form (for extra speed -- it converts them to native int anyway so it doesn't change the answer)

    @returns the distance between the two ids on the Great Circle
    """
    id1 = id_to_native_int(id1)
    id2 = id_to_native_int(id2)

    dif1 = abs(id1 - id2)
    dif2 = Size_of_NativeId_Int_Space - dif1
 
    return min(dif1, dif2)

def id_to_native_int(id, IntType=types.IntType, LongType=types.LongType, FloatType=types.FloatType):
    """
    This uses only the first 24 bits of `id', in order to be fast.  (If we used 32 bits, it would be slower due to using Python longs instead of a native int.)

    @param id can be one of the following four options: a native-int representation of an id, a float representation of a native-int, a full 160-bit id in either straight binary or mojosixbit-encoded form, or the prefix of an id, as long as it contains at least 24 bits of information and is in straight binary form, *not* in mojosixbit encoded form

    @precondition `id' must be an id or a native-int of an id, a float of an id, or else it must be the right length for a binary id prefix.: is_sloppy_id(id) or ((type(id) in (IntType, LongType, FloatType,)) and ((id >= 0) and (id < (2 ** 24)))) or ((len(id) >= 3) and (len(id) <= 20)): "id: %s :: %s" % (std.hr(id), std.hr(type(id)),)
    """
    assert is_sloppy_id(id) or ((type(id) in (IntType, LongType, FloatType,)) and ((id >= 0) and (id < (2 ** 24)))) or ((len(id) >= 3) and (len(id) <= 20)), "precondition: `id' must be an id or a native-int of an id, a float of an id, or else it must be the right length for a binary id prefix." + " -- " + "id: %s :: %s" % (std.hr(id), std.hr(type(id)),)

    typ = type(id)
    if typ is IntType or typ is LongType or typ is FloatType:
        return int(id)

    try:
        # std.mojolog.write("id: %s, %s, %s, %s\n" % (id, str(id), repr(id), std.hr(id),))
        nid = mojosixbit.a2b(id)
        if MojoConstants.DEBUG_MODE:
            if len(nid) < 20:
                std.mojolog.write("WARNING: `id_to_native_int()' called with a value that might have been ascii-encoded: id: %s, nid: %s.  Please fix it.\n" % (id, nid,), vs="debug", v=6)

        if len(nid) < 3:
            # Hm.  More than likely this was actually a binary, but short, string that happened to look like a mojosixbit encoded string.  Let's just put it back without complaining.
            nid = id
    except mojosixbit.Error:
        # Good -- it was not an ascii-encoded thing.
        nid = id
        pass

    return struct.unpack(">i", chr(0) + nid[:3])[0]

def int_to_id_prefix(i):
    """
    This generates only the first 24 bits of an id, from the most significant 24 bits of `i'.

    @param i an int or an id

    @precondition `i' must be an integer or an id.: is_sloppy_id(i) or (type(i) in ( types.IntType, types.LongType, )): "i: %s :: %s" % (std.hr(i), std.hr(type(i)))
    """
    assert is_sloppy_id(i) or (type(i) in ( types.IntType, types.LongType, )), "precondition: `i' must be an integer or an id." + " -- " + "i: %s :: %s" % (std.hr(i), std.hr(type(i)))

    if is_sloppy_id(i):
        return i

    C = 2**24

    while (i > C):
        i = i >> 8

    if type(id) in [ types.LongType, types.IntType ]:
        return struct.pack(">i", int(i))[1:]

def is_canonical_uniq(thing, _strtypes=_strtypes):
    """slightly slower than is_binary_id, but more accurate due to the type check"""
    if type(thing) not in _strtypes:
        return None
    return len(thing) == 20

def identifies(id, thing, thingtype=None):
    """
    @precondition `id' must be an id.: is_sloppy_id(id): "id: %s" % repr(id)
    """
    assert is_sloppy_id(id), "precondition: `id' must be an id." + " -- " + "id: %s" % repr(id)

    return equal(id, make_id(thing, thingtype))

def make_ascii_id(data):
    """Returns a nice simple 27 char ascii encoded id (sha1) of data"""
    return mojosixbit.b2a(string_to_id(data))

def string_to_id(sexpStr):
    """
    @param sexpStr the string containing the expression in canonical form

    @return the unique id of the sexp str

    @postcondition Result is of correct form.: is_binary_id(result)

    @precondition `sexpStr' must be a string.: type(sexpStr) == types.StringType: "sexpStr: %s" % repr(sexpStr)

    @memoizable

    @deprecated in favor of new name: `make_id()'
    """
    return make_id(sexpStr)

def make_id(thing, thingtype=None):
    """
    Use this function to create a unique persistent cryptographically assured id of a string.

    @param thing the thing that you want an id of
    @param thingtype optional type of the thing (ignored)

    @precondition `thing' must be a string.: type(thing) == types.StringType: "thing: %s :: %s" % (std.hr(thing), std.hr(type(thing)))

    """
    assert type(thing) == types.StringType, "precondition: `thing' must be a string." + " -- " + "thing: %s :: %s" % (str(thing), str(type(thing)))

    return sha.new(thing).digest()

def canonicalize(id, thingtype=None):
    """
    Use this function to canonicalize an id of one of the "bare" forms (a 20-byte binary string
    or the mojosixbit encoding thereof) into the canonical form.  Useful for calling on ids
    received from other brokers over the wire.

    @param id an id, which may be a bare binary or bare mojosixbit encoded id, or a full canonical id
    @param thingtype optional type of the thing that is identified (ignored)

    @returns the full canonical id

    @precondition `id' must be an id.: is_sloppy_id(id): "id: %s" % repr(id)
    """
    assert is_sloppy_id(id), "precondition: `id' must be an id." + " -- " + "id: %s" % repr(id)

    # NOTE: this method is also known as idlib.to_binary
    # implemented for speed not maintainability:
    if len(id) == 20:
        return id
    else:
        return mojosixbit.a2b(id)

def equal(id1, id2):
    """
    @returns `true' if and only if id1 and id2 identify the same thing;  if `id1' or `id2' or both are `None', then `equals()' returns false.

    @precondition `id1' must be `None' or an id.: (id1 is None) or is_sloppy_id(id1): "id1: %s" % repr(id1)
    @precondition `id2' must be `None' or an id.: (id2 is None) or is_sloppy_id(id2): "id2: %s" % repr(id2)
    """
    assert (id1 is None) or is_sloppy_id(id1), "precondition: `id1' must be `None' or an id." + " -- " + "id1: %s" % repr(id1)
    assert (id2 is None) or is_sloppy_id(id2), "precondition: `id2' must be `None' or an id." + " -- " + "id2: %s" % repr(id2)

    if (not id1) or (not id2):
        return None

    if len(id1) == len(id2):
        return id1 == id2

    if len(id1) == 27:
        assert len(id2) == 20
        return to_binary(id1) == id2
    else:
        assert len(id2) == 27
        assert len(id1) == 20
        return id1 == to_binary(id2)

# alternate name
equals = equal

def make_new_random_id(thingtype=None):
    return new_random_uniq()

def string_to_id(sexpStr):
    """
    @param sexpStr the string containing the expression in canonical form

    @return the unique id of the sexp str

    @postcondition Result is of correct form.: is_binary_id(result)

    @precondition `sexpStr' must be a string.: type(sexpStr) == types.StringType: "sexpStr: %s" % repr(sexpStr)

    @memoizable
    """
    assert type(sexpStr) == types.StringType, "precondition: `sexpStr' must be a string." + " -- " + "sexpStr: %s" % repr(sexpStr)

    return sha.new(sexpStr).digest()

def id_to_abbrev(str):
    """
    @precondition `str' must be an id.: is_sloppy_id(str): "str: %s" % repr(str)
    """
    if (len(str) == 27) and (_asciihash_re.match(str)):
        return "<" + str[:4] + ">"
    elif len(str) == 20:
        return "<" + mojosixbit.b2a(str[:3]) + ">"
    else:
        assert is_sloppy_id(str), "precondition: `str' must be an id." + " -- " + "str: %s" % repr(str)

# this gets called a -lot-, it must be fast!
def is_sloppy_id(astr, thingtype=None, _strtypes=_strtypes, _asciihash_re=_asciihash_re):
    return (type(astr) in _strtypes) and ((len(astr) == 20) or ((len(astr) == 27) and (_asciihash_re.match(astr))))

# this gets called a -lot-, it must be fast!
def is_mojosixbitencoded_id(str, thingtype=None, _asciihash_re=_asciihash_re):
    return (len(str) == 27) and (_asciihash_re.match(str))

is_ascii_id = is_mojosixbitencoded_id

# this gets called a -lot-, it must be fast!
def is_binary_id(str, thingtype=None):
    try:
        return len(str) == 20
    except:
        return None # 'false'

def is_id(str, thingtype=None):
    try:
        return len(str) == 20
    except:
        return None # 'false'

sloppy_id_to_bare_binary_id = canonicalize
to_binary = canonicalize

def to_mojosixbit(sid):
    """
    @precondition `sid' must be an id.: is_sloppy_id(sid): "sid: %s" % repr(sid)
    """
    if _asciihash_re.match(sid):
        return sid

    assert len(sid) == 20, "`sid' must be a mojosixbit or binary id." + " -- " + "sid: %s" % repr(sid)

    # then it must be binary, encode it
    return mojosixbit.b2a(sid)

to_ascii = to_mojosixbit

def newRandomUniq():
    """
    @return a universally unique random number

    @postcondition Result is of correct form.: is_canonical_uniq(result)

    @deprecated in favor of `new_random_uniq()'
    """
    return randsource.get(20)

new_random_uniq = newRandomUniq

std.is_sloppy_id = is_sloppy_id
std.is_canonical_uniq = is_canonical_uniq
std.is_mojosixbitencoded_id = is_mojosixbitencoded_id


def test_to_mojosixbit_is_idempotent():
    i = new_random_uniq()
    to_mojosixbit(i) == to_mojosixbit(to_mojosixbit(i))

#### generic stuff
mojo_test_flag = 1
def run():
    import RunTests
    RunTests.runTests(["idlib"])
    
#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


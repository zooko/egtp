#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
import evilcryptopp
import randsource


__doc__ = evilcryptopp._modval_doc
verify_key_and_value = evilcryptopp._modval_verify_key_and_value
verify_key = evilcryptopp._modval_verify_key
new = evilcryptopp._modval_new
new_random = evilcryptopp._modval_new_random
new_serialized = evilcryptopp._modval_new_serialized
Error = evilcryptopp.ModValError


def _help_test(size_n, pub_exp):
    import time
    import mojoutil

    starttime = time.time()
    servervalue = new_random(size_n, pub_exp)                  
    n = servervalue.get_modulus()
    e = servervalue.get_exponent()

    x = randsource.get(size_n)
    while verify_key_and_value(n, x):
        x = randsource.get(size_n)

    servervalue.set_value_string(x)
    servervalue.sign()
    y = servervalue.get_value()
    assert x != y

    servervalue.undo_signature()
    z = servervalue.get_value()
    assert x == z

    x = randsource.get(20)
    servervalue.set_value_string(x)
    servervalue.sign()
    y = servervalue.get_value()
    assert x != y

    servervalue.undo_signature()
    z = servervalue.get_value()

    # assert x == canon.strip_leading_zeroes(z) # can't use canon because of stupid circular import problems.  --Zooko 2000-09-04
    # Here is a cutnpasted implementation of canon.strip_leading_zeroes().  --Zooko 2000-09-07
    i = 0
    while (i < len(z)) and (z[i] == '\000'):
        i = i + 1
    z = z[i:]

    assert x == z

    stoptime = time.time()

    # debug.stderr.write("generating key, signing and checking signature took %s seconds with key size %s and public exponent %s.\n" % (`stoptime-starttime`, `size_n`, `pub_exp`))  # can't use debug because of stupid circular import problems.  --Zooko 2000-09-04
    print "generating key, signing and checking signature took %s seconds with key size %s and public exponent %s.\n" % (`stoptime-starttime`, `size_n`, `pub_exp`)


def DISABLED_FOR_FASTER_TESTS_test_25bytes_3():
    _help_test(25, 3)
   

def test_128bytes_3():
    _help_test(128, 3)
   

def DISABLED_FOR_FASTER_TESTS_test_128byte_17():
    _help_test(128, 17)
   

def DISABLED_FOR_FASTER_TESTS_test_128byte_65537():
    _help_test(128, 65537)
   

# Generic stuff
NAME_OF_THIS_MODULE="modval"

mojo_test_flag = 1

def run():
    import RunTests
    RunTests.runTests(NAME_OF_THIS_MODULE)

#### this runs if you import this module by itself
if __name__ == '__main__':
    run()



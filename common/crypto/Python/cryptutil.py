#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#



### our modules
from mojostd import cryptutilError, OAEPError, oaep, oaep_decode, xor, hmac, hmacish, mgf1, get_rand_lt_n, get_rand_lt_n_with_prepended_0

import tripledescbc
import HashRandom



def hashexpand(inpstr, expbytes, HRClass=HashRandom.SHARandom):
    return HRClass(inpstr).get(expbytes)

def dummy_encrypt(cleartext, key):
    return cleartext

def dummy_decrypt(cleartext, key):
    return cleartext

def desx_encrypt(cleartext, key):
    """
    This is a very thin wrapper over `tripledescbc', providing a small simplification of
    combining key and iv into one `key', and providing a functionish rather than objectish
    interface.
    """
    # Could try to assert that `key' is long and probably random...  --Zooko 2000-09-22

    return tripledescbc.new(HashRandom.hashexpand(key + 'key', 24)).encrypt(HashRandom.hashexpand(key + 'iv', 8), cleartext)

def desx_decrypt(ciphertext, key):
    """
    This is a very thin wrapper over `tripledescbc', providing a small simplification of
    combining key and iv into one `key', and providing a functionish rather than objectish
    interface.
    """
    # Could try to assert that `key' is long and probably random...  --Zooko 2000-09-22

    return tripledescbc.new(HashRandom.hashexpand(key + 'key', 24)).decrypt(HashRandom.hashexpand(key + 'iv', 8), ciphertext)


mojo_test_flag = 1

#### generic stuff
def run():
    import RunTests
    RunTests.runTests(["cryptutil"])
    
#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


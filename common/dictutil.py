#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

import exceptions
import types
true = 1
false = 0

def prune_empties(dict, keys, strict=false):
    """
    Remove any of the subtrees of `keys' which are empty.
    If `strict' raise an exception if the whole branch isn't present.
    """
    if len(keys) == 0:
        return

    try:
        prune_empties(dict[keys[0]], keys[1:])
    except KeyError:
        if strict:
            raise

    try:
        if len(keys) == 1:
            if len(dict[keys[0]]) == 0:
                del dict[keys[0]]
    except KeyError:
        if strict:
            raise

def del_if_present(dict, key):
    if dict.has_key(key):
        del dict[key]

def recursive_dict_update(a, b):
    '''This is much like a.update(b), except when a value in b is a dict, it
    recurses.  Thus it acts "deep" instead of "shallow".'''
    for k, v in b.items():
        if type(v) == types.DictType:
            try:
                try:
                    recursive_dict_update(a[k], v)
                except KeyError:
                    # a[k] is not defined yet, so:
                    a[k] = {}
                    recursive_dict_update(a[k], v)
            except exceptions.StandardError, le:
                le.args = (le.args, "in `recursive_dict_update(%s[%s], %s)" % (`a`, `k`, `v`))
                raise le
        else:
            a[k] = v
    return

def add_num_to_dict(dict, key, val, default=0):
    """
    If the key doesn't appear in dict then it is created with value default (before addition).
    """
    dict[key] = dict.get(key, default) + val

def inc(dict, key):
    """
    Increment the value associated with `key' in `dict'.  If there is no such key, then one will be created with initial value 1 (after `inc()').
    """
    try:
        add_num_to_dict(dict, key, 1)
    except OverflowError:
        add_num_to_dict(dict, key, 1L)

def items_sorted_by_val(dict):
    """
    @return a list of (key, value,) pairs sorted according to val
    """
    l = map(lambda x: (x[1], x[0],), dict.items())
    l.sort()
    return map(lambda x: (x[1], x[0],), l)

def subtract_num_from_dict(dict, key, val):
    """
    If the value goes down to 0 then the key is removed from the dict.

    If the value goes down to less than zero then an exception is raised.
    """
    old = dict.get(key)
    if not old:
        raise "bad usage"
    else:
        new = old - val
        if new == 0:
            del dict[key]
        else:
            dict[key] = new

def add_nums(d1, d2):
    """
    All of the values of `d1' and `d2' should be numbers.
    Mutate `d1' by adding the values from `d2' to the corresponding keys in `d1', treating absent keys in `d1' as if they have value 0.
    """
    for k, v in d2.items():
        add_num_to_dict(d1, k, v)

def _our_setdefault(dict, key, value):
    """
    setdefault(dict, key, value) is equivalent to
    dict.setdefault(key, value) in python 2.0.
    """
    # XXX Once we require Python >= 2.0 we can
    # do away with this function and use the
    # dict method of the same name.
    if not dict.has_key(key):
        dict[key] = value
    return dict[key]

def _python_setdefault(dict, key, value):
    return dict.setdefault(key, value)

# If the interpreter provides a native `setdefault' for this dict then use it, else define one:
# (This is for backwards compatibility with python 1.5.2.)
# Note that this means that a dict-like class that we have defined, which does *not* have
# its own `setdefault()' method defined, will work under 1.5.2 and not under 2.0 or greater!
# See also `popitem()'.
# I think the Right Solution to this is for the dict-like thing to subclass UserDict...
try:
    d = {}
    d.setdefault("test", "test")

    setdefault = _python_setdefault
except AttributeError:
    setdefault = _our_setdefault
    pass

def _our_popitem(dict):
    k = dict.keys()[0]
    v = dict[k]
    del dict[k]
    return (k, v,)

def _python_popitem(dict):
    return dict.popitem()

# If the interpreter provides a native `popitem' for this dict then use it, else define one:
# (This is for backwards compatibility with python <= 2.0.)
# Note that this means that a dict-like class that we have defined, which does *not* have
# its own `popitem()' method defined, will work under 2.0 or lesser and not under 2.1 or greater!
# See also `setdefault()'.
# I think the Right Solution to this is for the dict-like thing to subclass UserDict...
try:
    d = {'spam':'eggs'}
    d.popitem()

    popitem = _python_popitem
except AttributeError:
    popitem = _our_popitem
    pass

mojo_test_flag = 1

#### generic stuff
def run():
    import RunTests
    RunTests.runTests(["dictutil"])
    
#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

import std
# import traceback # debugging

class wrappedmethod:
    def __init__(self, func):
        self.__func = func
        self.__name__ = "wrapped" + func.__name__

    def __repr__(self):
        return "<wrappedmethod: %s>" % self.__func

    def __call__(self, *args, **kwargs): 
        # print "args: %s, kwargs: %s, self.__func: %s, traceback: %s" % (`args`, `kwargs`, `self.__func`, `traceback.extract_stack()`)
        assert hasattr(args[0], '_Locker__enter'), "args: %s, kwargs: %s, args[0]: %s :: %s, dir(): %s" % (std.hr(args), std.hr(kwargs), std.hr(args[0]), std.hr(type(args[0])), std.hr(dir(args[0])),)
        assert hasattr(args[0], '_Locker__exit'), "args: %s, kwargs: %s, args[0]: %s :: %s, dir(): %s" % (std.hr(args), std.hr(kwargs), std.hr(args[0]), std.hr(type(args[0])), std.hr(dir(args[0])),)
        # args[0]._THINGIE = "hello!" # testing.
        args[0]._Locker__enter()
        try:
            return apply(self.__func, args, kwargs)
        finally:
            args[0]._Locker__exit()

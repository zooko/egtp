#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

### standard modules
import exceptions
import os

### our modules
true = 1
false = 0
import mojosixbit
import randsource
import std

def get_tempfile_name(tmpdir='/tmp', pre='', post=''):
    """
    This returns a suitable temporary filename tuple in the form (tmpdir, tempfile).
        tempfile is the string pre, followed by the random element, followed by post.
        tmpdir is the directory this file should be stored in.  
            (I suggest using os.path.expandvars(confman.dict["PATH"]["TMP_DIR"]))

    Handy trick: Using apply(os.path.join, get_tempfile_name()) gives an absolute path.
    """
    tempfile = '.'
    while os.path.exists(os.path.join(tmpdir, tempfile)):
        tempfile = pre + mojosixbit.b2a(randsource.get(6)) + post
    return (tmpdir, tempfile)

def make_dirs(dirname, mode=0700):
    """
    This is an idempotent "make_dirs()".
    If the dir already exists, return `true'.  If this call creates the dir, return `true'.  If
    there is an error that prevents creation, raise the OS error.
    """
    tx = None
    try:
        os.makedirs(dirname, mode)
    except OSError, x:
        tx = x

    if not os.path.isdir(dirname):
        if tx:
            raise tx
        raise exceptions.IOError, "unknown error prevented creation of directory: %s" % dirname # careful not to construct an IOError with a 2-tuple, as that has a special meaning...

def rmrf(dirname):
    try:
        for f in os.listdir(dirname):
            fullname = os.path.join(dirname, f)
            if os.path.isdir(fullname):
                rmrf(fullname)
                os.rmdir(fullname)
            else :
                os.remove(fullname)
    except OSError, le:
        if hasattr(le, 'args'):
            if (le.args[0] == 2) or (le.args[1] == 'No such file or directory'):
                # Fine.  It's gone!
                return
        raise

mojo_test_flag = 1

#### generic stuff
def run():
    import RunTests
    RunTests.runTests(["fileutil"])
    
#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


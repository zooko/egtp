#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.

# CVS:
__cvsid = '$Id: IRemoteOpHandler.py,v 1.1 2002/04/11 13:59:23 zooko Exp $'

# standard Python modules
import exceptions

class NotImplementedError(exceptions.StandardError): pass

class IRemoteOpHandler:
    """
    This is an "interface" class, which in Python means that it is really just a form of documentation.  Hello, hackers!

    A "remote op handler" is an object which handles the results of one specific remote operation.
    """
    def __init__(self):
        pass

    def result(self, object):
        """
        The results are in!
        """
        raise NotImplementedError
        pass

    def fail(self, reason=""):
        """
        Your remote op manager invokes this to let you know that he absolutely positively cannot get
        the result you were looking for.  There is no chance that he will later call `result()' for
        this operation.  You can safely forget all about this particular operation.

        @param reason a string describing why it failed (used for human-readable diagnostic output)
        """
        raise NotImplementedError
        pass

    def soft_timeout(self):
        """
        Your remote op manager invokes this to let you know that time has passed and the results
        have not come in.  You might want to use this opportunity to get impatient and do something
        else.  However, the results might still come in, in which case your remote op manager will
        call `result()', just as if the results had come in more promptly.

        A "hard" timeout, which means that the remote op manager gives up and will ignore any
        results which come in after this point, is signalled by a call to `fail()'.
        """
        raise NotImplementedError
        pass


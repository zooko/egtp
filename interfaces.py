#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: interfaces.py,v 1.1 2002/01/29 20:07:05 zooko Exp $'

# standard Python modules
import exceptions

class NotImplementedError(exceptions.StandardError): pass

class ILookupManager:
    """
    This is an "interface" class, which in Python means that it is really just a form of
    documentation.  Hello, hackers!
    """
    def __init__(self):
        pass

    def lookup(self, key, lookuphand):
        """
        @param key the key of the thing to be looked up;  This key must be self-authenticating,
            i.e. given this key and the resulting object, the lookup manager must be able to
            determine whether or not the object is a valid object for the key even if the object is
            a bogus object manufactured by a powerful and malicious attacker.  (If you don't have
            self-authenticating keys, use a discovery manager instead.)
        @param lookuphand an object which satisfies the ILookupHandler interface
        """
        raise NotImplementedError
        pass

    def publish(self, key, object):
        """
        @param key the key by which the object can subsequently to be looked up;  This key must be
            self-authenticating, i.e. given this key and an object, a lookup manager must be able
            to determine whether or not the object is *this* object even if the object is a bogus
            object manufactured by a powerful and malicious attacker.  (If you don't have self-
            authenticating keys, use a discovery manager instead.)
        @param object the thing to be published
        """
        raise NotImplementedError
        pass

class ILookupHandler:
    """
    This is an "interface" class, which in Python means that it is really just a form of documentation.  Hello, hackers!

    A "lookup handler" is an object which handles the results of one individual attempt to lookup.
    """
    def __init__(self):
        pass

    def result(self, value):
        """
        The results are in!  Your lookup manager will already have verified that this value is
        cryptographically proven to match the self-authenticating key.  You can now do what you want
        with the results.
        """
        raise NotImplementedError
        pass

    def fail(self, reason=""):
        """
        Your lookup manager invokes this to let you know that he absolutely positively cannot find
        the thing you were looking for.  There is no chance that he will later call `result()' for
        this query.  You can safely forget all about this particular query.

        @param reason a string describing why it failed (used for human-readable diagnostic output)
        """
        raise NotImplementedError
        pass

    def soft_timeout(self):
        """
        Your lookup manager invokes this to let you know that time has passed and the results have
        not come in.  You might want to use this opportunity to get impatient and do something else.
        However, the results might still come in, in which case your lookup manager will call
        `result()', just as if the results had come in more promptly.

        A "hard" timeout, which means that the lookup manager gives up and will ignore any results
        which come in after this point, is signalled by a call to `fail()'.
        """
        raise NotImplementedError
        pass

class IDiscoveryManager:
    """
    This is an "interface" class, which in Python means that it is really just a form of documentation.  Hello, hackers!
    """
    def __init__(self):
        pass

    def discover(self, query, discoveryhand):
        """
        @param query the query describing the kind of thing you want to discover;  If the query is
            self-authenticating, (i.e. given this query and the resulting object, the lookup manager
            is able to determine whether or not the object is a valid object for the key even if the
            object is a bogus object manufactured by a powerful and malicious attacker), then you
            should use a lookup manager instead of a discovery manager.  (The lookup manager will
            perform that verification for you.)
        @param discoveryhand an object which satisfies the IDiscoveryHandler interface
        """
        raise NotImplementedError
        pass

    def publish(self, metadata, object):
        """
        @param metadata some metadata by which the object can subsequently to be discovered
        @param object the thing to be published
        """
        raise NotImplementedError
        pass

class IDiscoveryHandler:
    """
    This is an "interface" class, which in Python means that it is really just a form of
    documentation.  Hello, hackers!

    A "discovery handler" is an object which handles the results of an individual query.
    """
    def __init__(self):
        pass

    def result(self, value):
        """
        The results are in!  You can now do what you want with the results.  Note that `None' is a
        valid result.  Whether your discovery manager chooses to tell you that the answer is `None',
        or whether he chooses to keep searching for a non-None answer is up to him.
        """
        raise NotImplementedError
        pass

    def fail(self, reason=""):
        """
        Your discovery manager invokes this to let you know that he absolutely positively cannot
        find the kind of things you were looking for.  There is no chance that he will later call
        `result()' for this query.  You can safely forget all about this particular query.

        When does the discovery manager call `fail()' instead of calling `result(None)'?  The answer
        is that `fail()' should indicate a technical failure (for example, the discovery man was
        unable to send the query out, or the nodes that he queried did not send a response in a
        timely way even though they were expected to do so), and `result(None)' should indicate that
        everything is working fine as far as the discovery man can tell, but nobody knows the answer
        to your query (for example, a reasonable number of nodes responded in a timely manner, but 
        they all said they had no answer).  This distinction is necessarily fuzzy, but it can be
        important as technical failure can trigger attempts to try alternate routes or to rebuild
        your network, etc..

        @param reason a string describing why it failed (used for human-readable diagnostic output)
        """
        raise NotImplementedError
        pass

    def soft_timeout(self):
        """
        Your discoveryl manager invokes this to let you know that time has passed and the results
        have not come in.  You might want to use this opportunity to get impatient and do something
        else.  However, the results might still come in, in which case your discovery manager will
        call `result()', just as if the results had come in more promptly.

        A "hard" timeout, which means that the lookup manager gives up and will ignore any results
        which come in after this point, is signalled by a call to `fail()'.
        """
        raise NotImplementedError
        pass 

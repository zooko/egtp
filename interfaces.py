#!/usr/bin/env python

#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  portions Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: interfaces.py,v 1.3 2002/03/28 18:39:50 zooko Exp $'

# standard Python modules
import exceptions

# pyutil modules
from humanreadable import hr

# EGTP modules
from IRemoteOpHandler import IRemoteOpHandler

class NotImplementedError(exceptions.StandardError): pass

class IVerifier:
    """
    Determines whether a key -> object mapping is legitimate.
    """
    def __init__(self):
        pass

    def verify_mapping(self, key, object):
        """
        @returns true if and only if `object' is a valid result for `key'

        @precondition key must be well-formed.: self.verify_key(key): "key: %s" % hr(key)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        assert self.verify_key(key), "precondition: key must be well-formed." + " -- " + "key: %s" % hr(key)
        raise NotImplementedError
        pass

    def verify_key(self, key):
        """
        @returns true if and only if `key' is well-formed

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        raise NotImplementedError
        pass

class ILookupManager:
    """
    Performs lookups and publications.
    """
    def __init__(self, verifier):
        """
        @param a verifier object

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        self.verifier = verifier
        pass

    def lookup(self, key, lookuphand):
        """
        @param key the key of the thing to be looked up;  This key must be self-authenticating,
            i.e. given this key and the resulting object, the lookup manager must be able to
            determine whether or not the object is a valid object for the key even if the object is
            a bogus object manufactured by a powerful and malicious attacker.  (If you don't have
            self-authenticating keys, use a discovery manager instead.)
        @param lookuphand an object which satisfies the ILookupHandler interface

        @precondition key must be well-formed according to the verifier.: self.verifier.verify_key(key): "key: %s" % hr(key)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        assert self.verifier.verify_key(key), "precondition: key must be well-formed according to the verifier." + " -- " + "key: %s" % hr(key)
        raise NotImplementedError
        pass

    def publish(self, key, object, publishhand=None):
        """
        @param key the key by which the object can subsequently to be looked up;  This key must be
            self-authenticating, i.e. given this key and an object, a lookup manager must be able
            to determine whether or not the object is *this* object even if the object is a bogus
            object manufactured by a powerful and malicious attacker.  (If you don't have self-
            authenticating keys, use a discovery manager instead.)
        @param object the thing to be published
        @param publishhand an object which satisfies the IRemoteOpHandler interface, or `None'

        @precondition key must be well-formed according to the verifier.: self.verifier.verify_key(key): "key: %s" % hr(key)
        @precondition key-object pair must be valid mapping according to the verifier.: self.verifier.verify_mapping(key, object): "key: %s, object: %s" % (hr(key), hr(object),)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        assert self.verifier.verify_key(key), "precondition: key must be well-formed according to the verifier." + " -- " + "key: %s" % hr(key)
        assert self.verifier.verify_mapping(key, object), "precondition: key-object pair must be valid mapping according to the verifier." + " -- " + "key: %s, object: %s" % (hr(key), hr(object),)
        raise NotImplementedError
        pass

class ILookupHandler(IRemoteOpHandler):
    """
    Handles the results of one individual attempt to lookup.
    """
    def __init__(self, key, verifier):
        """
        @param the key that you are trying to look up
        @param a verifier object

        @precondition key must be well-formed.: verifier.verify_key(key): "key: %s" % hr(key)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        assert verifier.verify_key(key), "precondition: key must be well-formed." + " -- " + "key: %s" % hr(key)
        self.key = key
        self.verifier = verifier
        pass

    def result(self, object):
        """
        The results are in!  Your lookup manager will already have verified that this object is
        cryptographically proven to match the self-authenticating key.  You can now do what you want
        with the results.

        @precondition key-object pair must be valid mapping according to the verifier.: self.verifier.verify_mapping(self.key, object): "self.key: %s, object: %s" % (hr(self.key), hr(object),)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        assert self.verifier.verify_mapping(self.key, object), "precondition: key-object pair must be valid mapping according to the verifier." + " -- " + "self.key: %s, object: %s" % (hr(self.key), hr(object),)
        raise NotImplementedError
        pass

    def fail(self, reason=""):
        """
        Your lookup manager invokes this to let you know that he absolutely positively cannot find
        the thing you were looking for.  There is no chance that he will later call `result()' for
        this query.  You can safely forget all about this particular query.

        @param reason a string describing why it failed (used for human-readable diagnostic output)

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
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

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        raise NotImplementedError
        pass

class IDiscoveryManager:
    """
    Performs discoveries and discoverable publications.
    """
    def __init__(self):
        """
        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
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

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        raise NotImplementedError
        pass

    def publish(self, metadata, object, publishhand=None):
        """
        @param metadata some metadata by which the object can subsequently to be discovered
        @param object the thing to be published
        @param publishhand an object which satisfies the IRemoteOpHandler interface, or `None'

        @noblock This method may not block, either by waiting for network traffic, by waiting for a lock, or by sleeping.
        """
        raise NotImplementedError
        pass

class IDiscoveryHandler(IRemoteOpHandler):
    """
    Handles the results of an individual discovery query.
    """
    def __init__(self):
        pass

    def result(self, object):
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

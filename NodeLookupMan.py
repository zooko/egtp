#!/usr/bin/env python
#
# Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
# mailto:zooko@zooko.com
# See the end of this file for the free software, open source license (BSD-style).

# CVS:
__cvsid = '$Id: NodeLookupMan.py,v 1.2 2002/03/16 14:14:34 zooko Exp $'

# standard Python modules
import exceptions
import types

# pyutil modules
from humanreadable import hr

# EGTP modules
import CommStrat
import interfaces

# (old) MN modules
import idlib

class NodeLookupMan(interfaces.ILookupManager):
    """
    This wraps a lookup manager and translates from native EGTP Python objects into serialized keys
    and values before publish.

    It also asserts the validity of the key->value mapping before publish.  It also asserts that
    the key is well-formed before publish and before lookup.
    """
    def __init__(self, lm):
        """
        @param lm the lookup manager object that implements publish and lookup
        """
        interfaces.ILookupManager.__init__(self)
        self.lm = lm

    def lookup(self, key, lookuphand):
        """
        @precondition key must be an id.: idlib.is_id(key): "key: %s :: %s" % (hr(key), hr(type(key)),)
        """
        assert idlib.is_id(key), "precondition: key must be an id." + " -- " + "key: %s :: %s" % (hr(key), hr(type(key)),)

        self.lm.lookup(key, NodeLookupHand(lookuphand, key))

    def publish(self, key, object):
        """
        @precondition key must be an id.: idlib.is_id(key): "key: %s :: %s" % (hr(key), hr(type(key)),)
        @precondition object must be a dict with a ["connection strategies"][0]["pubkey"] key chain, or else a CommStrat instance with a broker_id.: ((type(object) is types.DictType) and (object.has_key("connection strategies")) and (object.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(object) is types.InstanceType) and (isinstance(object, CommStrat)) and (object._broker_id is not None)): "object: %s :: %s" % (hr(object), hr(type(object)),)
        @precondition key must match object.: idlib.equal(key, CommStrat.addr_to_id(object)): "key: %s, object: %s" % (hr(key), hr(object),)
        """
        assert idlib.is_id(key), "precondition: key must be an id." + " -- " + "key: %s :: %s" % (hr(key), hr(type(key)),)
        assert ((type(object) is types.DictType) and (object.has_key("connection strategies")) and (object.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(object) is types.InstanceType) and (isinstance(object, CommStrat)) and (object._broker_id is not None)), "precondition: object must be a dict with a [\"connection strategies\"][0][\"pubkey\"] key chain, or else a CommStrat instance with a broker_id." + " -- " + "object: %s :: %s" % (hr(object), hr(type(object)),)
        assert idlib.equal(key, CommStrat.addr_to_id(object)), "precondition: key must match object." + " -- " + "key: %s, object: %s" % (hr(key), hr(object),)

        self.lm.publish(key, object)

class NodeLookupHand(interfaces.ILookupHandler):
    """
    This wraps a lookup handler and translates from serialized values into native EGTP Python
    objects after lookup.

    It also asserts the validity of the key->value mapping after lookup.
    """
    def __init__(self, lh, key):
        """
        @param lh the lookup handler object

        @precondition key must be an id.: idlib.is_id(key): "key: %s :: %s" % (hr(key), hr(type(key)),)
        """
        assert idlib.is_id(key), "precondition: key must be an id." + " -- " + "key: %s :: %s" % (hr(key), hr(type(key)),)

        interfaces.ILookupHandler.__init__(self)
        self.lh = lh
        self.key = key

    def result(self, object):
        """
        @precondition self.key must be an id.: idlib.is_id(self.key): "self.key: %s :: %s" % (hr(self.key), hr(type(self.key)),)
        @precondition object must be a dict with a ["connection strategies"][0]["pubkey"] key chain, or else a CommStrat instance with a broker_id.: ((type(object) is types.DictType) and (object.has_key("connection strategies")) and (object.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(object) is types.InstanceType) and (isinstance(object, CommStrat)) and (object._broker_id is not None)): "object: %s :: %s" % (hr(object), hr(type(object)),)
        @precondition self.key must match object.: idlib.equal(self.key, CommStrat.addr_to_id(object)): "self.key: %s, object: %s" % (hr(self.key), hr(object),)
        """
        assert idlib.is_id(self.key), "precondition: self.key must be an id." + " -- " + "self.key: %s :: %s" % (hr(self.key), hr(type(self.key)),)
        assert ((type(object) is types.DictType) and (object.has_key("connection strategies")) and (object.get("connection strategies", [{}])[0].has_key("pubkey"))) or ((type(object) is types.InstanceType) and (isinstance(object, CommStrat)) and (object._broker_id is not None)), "precondition: object must be a dict with a [\"connection strategies\"][0][\"pubkey\"] key chain, or else a CommStrat instance with a broker_id." + " -- " + "object: %s :: %s" % (hr(object), hr(type(object)),)
        assert idlib.equal(self.key, CommStrat.addr_to_id(object)), "precondition: self.key must match object." + " -- " + "self.key: %s, object: %s" % (hr(self.key), hr(object),)

        self.lh.result(object)

    def fail(self, reason=""):
        self.lh.fail(reason)

    def soft_timeout(self):
        self.lh.soft_timeout()

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software to deal in this software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of this software, and to permit
# persons to whom this software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of this software.
#
# THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THIS SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THIS SOFTWARE.

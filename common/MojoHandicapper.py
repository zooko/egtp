#!/usr/bin/env python
#
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: MojoHandicapper.py,v 1.3 2002/06/25 02:12:27 zooko Exp $'


# Python standard library modules
import bisect
import traceback
import types

# pyutil modules
import DoQ
from debugprint import debugprint, debugstream
from compat import setdefault
import humanreadable

# (old-)EGTP modules
import idlib
import mojoutil

DISQUALIFIED = ()

def getnameofhandicapper(thingie):
    if hasattr(thingie, '__name__'):
        if thingie.__name__ != "compute_handicap":
            return thingie.__name__

    if hasattr(thingie, 'im_class'):
        return getnameofhandicapper(thingie.im_class)

    if hasattr(thingie, '__class__'):
        return getnameofhandicapper(thingie.__class__)

    return humanreadable.hr(thingie)

class MojoHandicapper :
    """
    A very simple business logic utility - for each message to be sent out, compute the 
    sum of all estimated real costs of it, and sort based on those.
    
    Available methods are add_handicapper and sort_by_preference
    """
    def __init__(self) :
        self.__handicappers_map = {None: []}   # maps from message type to a list of handicappers (None = all messages)
        
    def add_handicapper(self, handicapper, mtypes=None) :
        """
        Adds a handicap computing function to the list of all of them.

        A handicap function must take the parameters counterparty_id, message_type, and
        message_body and return a float value or DISQUALIFIED.

        @param mtypes if specified is a list of message types this handicapper
        should be applied to (None indicates all message types).
        [message type specific handicappers will always be evaulated before generic handicappers]

        Sum of squares addition is used: All results are squared before being used.

        Numerical values will be added to produce a total handicap. DISQUALIFIED
        will completely disqualify the given counterparty.

        A sophisticated reputation system could be plugged in here -- if you had information
        from friends of friends indicating that a given counterparty is unreliable, you could
        make a handicapper which returns your friend's friend's opinion, and it will be factored
        in along with the other considerations.

        @precondition `handicapper' must be a callable.: callable(handicapper): "handicapper: %s :: %s" % (humanreadable.hr(handicapper), `type(handicapper)`)
        @precondition `mtypes' must be None or a sequence.: (mtypes is None) or (type(mtypes) in (types.ListType, types.TupleType,))
        """
        assert callable(handicapper), "precondition: `handicapper' must be a callable." + " -- " + "handicapper: %s :: %s" % (humanreadable.hr(handicapper), `type(handicapper)`)
        assert (mtypes is None) or (type(mtypes) in (types.ListType, types.TupleType,)), "precondition: `mtypes' must be None or a sequence."

        if mtypes is None:
            self.__handicappers_map[None].append(handicapper)
        else:
            for mtype in mtypes:
                setdefault(self.__handicappers_map, mtype, []).append(handicapper)
        
    def _compute_handicap(self, counterparty_id, metainfo, message_type, message_body):
        """
        Computes the 'handicap', or estimated real cost including risk of failure, 
        of sending the message to the counterparty.

        @precondition This method must be called on the DoQ.: DoQ.doq.is_currently_doq()
        @precondition `counterparty_id' must be a binary id.: idlib.is_binary_id(counterparty_id): "counterparty_id: %s" % humanreadable.hr(counterparty_id)
        """
        assert DoQ.doq.is_currently_doq(), "precondition: This method must be called on the DoQ."
        assert idlib.is_binary_id(counterparty_id), "precondition: `counterparty_id' must be a binary id." + " -- " + "counterparty_id: %s" % humanreadable.hr(counterparty_id)

        handicap = 0.0
        _hmap = self.__handicappers_map
        for h in (_hmap.get(message_type, []) + _hmap[None]) :
            try:
                amount = h(counterparty_id = counterparty_id, metainfo = metainfo, message_type = message_type, message_body = message_body)
            except:
                debugprint("WARNING: counterparty %s disqualified due to exception:\n Handicapper Params (message_type=%s, message_body=%s, metainfo=%s)\n:", args=(counterparty_id, message_type, message_body, metainfo), v=2, vs="business logic")
                traceback.print_exc(file=debugstream)
                return DISQUALIFIED

            assert amount is DISQUALIFIED or (type(amount) is types.FloatType), "Handicapper function must return certain type. -- func: %s, result: %s, counterparty_id: %s, metainfo: %s\n" % (humanreadable.hr(h), humanreadable.hr(amount), humanreadable.hr(counterparty_id), humanreadable.hr(metainfo)) # postcondition

            if amount is DISQUALIFIED :
                # debugprint("Handicap %s DISQUALIFIED for %s on %s\n", args=(getnameofhandicapper(h), counterparty_id, message_type), v=2, vs="business logic")
                return DISQUALIFIED
            else:
                assert amount >= 0.0
                # debugprint("Handicap %s additive %s for %s on %s\n", args=(getnameofhandicapper(h), "%0.0f" % amount, counterparty_id, message_type), v=2, vs="business logic")
                handicap = handicap + (amount**2)
        # debugprint("Handicap %s for %s on %s\n", args=("%0.0f" % handicap, counterparty_id, message_type), v=2, vs="business logic")
        return handicap

    def pick_best(self, counterparties, message_type, message_body):
        """
        @returns the id of the best (lowest handicap, not DISQUALIFIED) counterparty, or `None' if none (i.e., they were all disqualified, or the input `counterparties' was of length 0)

        @param counterparties a sequence of (counterparty_id, service_info_dict);  It is okay to be an empty list.

        @precondition `counterparties' must be a sequence of (id, infodict,) tuples.: (type(counterparties) in (types.ListType, types.TupleType,)) and (len(filter(lambda x: not ((type(x) in (types.TupleType, types.DictType,)) and (len(x) == 2) and idlib.is_sloppy_id(x[0])), counterparties)) == 0): "counterparties: %s" % humanreadable.hr(counterparties)
        """
        assert (type(counterparties) in (types.ListType, types.TupleType,)) and (len(filter(lambda x: not ((type(x) in (types.TupleType, types.DictType,)) and (len(x) == 2) and idlib.is_sloppy_id(x[0])), counterparties)) == 0), "precondition: `counterparties' must be a sequence of (id, infodict,) tuples." + " -- " + "counterparties: %s" % humanreadable.hr(counterparties)

        best = None
        bestcost = None
        for (cpid, info,) in counterparties:
            cost = self._compute_handicap(cpid, info, message_type=message_type, message_body=message_body)
            if cost is not DISQUALIFIED :
                if (bestcost is None) or (cost < bestcost):
                    bestcost = cost
                    best = cpid
        return best

    def pick_best_from_dict(self, counterparties, message_type, message_body):
        """
        @param counterparties a dict of key: counterparty_id, value: service_info_dict;  It is okay to be an empty dict.

        @returns the id of the best (lowest handicap, not DISQUALIFIED) counterparty, or `None' if none (i.e., they were all disqualified, or the input `counterparties' was of length 0)
        """
        best = None
        bestcost = None
        for cpid, info in counterparties.items():
            cost = self._compute_handicap(cpid, info, message_type=message_type, message_body=message_body)
            if cost is not DISQUALIFIED :
                if (bestcost is None) or (cost < bestcost):
                    bestcost = cost
                    best = cpid
        return best

    def sort_by_preference_from_dict(self, counterparties, message_type, message_body):
        """
        @param counterparties a dict of key: counterparty_id, value: service_info_dict;  It is okay to be an empty dict.

        Cogitates on the possibility of sending each counterparty in counterparties 
        the given message and returns a list sorted by order of preference of which 
        counterparties to try to use. Disqualified counterparties are not included 
        in the list at all.

        @returns a list of (counterpartyid, info) tuples sorted into descending order of preference

        @precondition `counterparties' must be a dict.: type(counterparties) is types.DictType: "counterparties: %s :: %s" % (humanreadable.hr(counterparties), humanreadable.hr(type(counterparties)),)
        @precondition `message_type' must be a string.: type(message_type) == types.StringType
        """
        assert type(counterparties) is types.DictType, "precondition: `counterparties' must be a dict." + " -- " + "counterparties: %s :: %s" % (humanreadable.hr(counterparties), humanreadable.hr(type(counterparties)),)
        assert type(message_type) == types.StringType, "precondition: `message_type' must be a string."

        # debugprint("sort_by_preference_dict(counterparties: %s, message_type:%s, message_body: %s)\n", args=(counterparties, message_type, message_body,), v=2, vs="MojoHandicapper")

        # contains (counterparty_id, cost)
        unsorted = []
        for counterpartyid, contactinfo in counterparties.items():
            cost = self._compute_handicap(counterpartyid, contactinfo, message_type=message_type, message_body=message_body)
            if cost is not DISQUALIFIED :
                unsorted.append((cost, i))
        unsorted.sort()
        return map(lambda x: x[1], unsorted)

    def sort_by_preference(self, counterparties, message_type, message_body):
        """
        @param counterparties a sequence of (counterparty_id, service_info_dict);  It is okay to be an empty list.

        Cogitates on the possibility of sending each counterparty in counterparties 
        the given message and returns a list sorted by order of preference of which 
        counterparties to try to use. Disqualified counterparties are not included 
        in the list at all.

        @precondition `counterparties' must be a sequence of (id, infodict,) tuples.: (type(counterparties) in (types.ListType, types.TupleType,)) and (len(filter(lambda x: not ((type(x) in (types.TupleType, types.DictType,)) and (len(x) == 2) and idlib.is_sloppy_id(x[0])), counterparties)) == 0): "counterparties: %s" % humanreadable.hr(counterparties)
        @precondition `message_type' must be a string.: type(message_type) == types.StringType
        """
        assert (type(counterparties) in (types.ListType, types.TupleType,)) and (len(filter(lambda x: not ((type(x) in (types.TupleType, types.DictType,)) and (len(x) == 2) and idlib.is_sloppy_id(x[0])), counterparties)) == 0), "precondition: `counterparties' must be a sequence of (id, infodict,) tuples." + " -- " + "counterparties: %s" % humanreadable.hr(counterparties)
        assert type(message_type) == types.StringType, "precondition: `message_type' must be a string."

        # debugprint("sort_by_preference(counterparties: %s, message_type:%s, message_body: %s)\n", args=(counterparties, message_type, message_body,), v=2, vs="MojoHandicapper")

        # contains (counterparty_id, cost)
        unsorted = []
        for i in counterparties :
            cost = self._compute_handicap(i[0], i[1], message_type=message_type, message_body=message_body)
            if cost is not DISQUALIFIED :
                unsorted.append((cost, i))
        unsorted.sort()
        return map(lambda x: x[1], unsorted)

mojo_test_flag = 1

def test_disqualified_not_returned() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return DISQUALIFIED
        else :
            return 0
    h.add_handicapper(cfunc)
    result = h.sort_by_preference(counterparty_ids = [(id_a, None), (id_b, None)], message_type = 'a message', message_body = {})
    assert len(result) == 1
    assert result[0][0] == id_b

def test_returns_nothing_for_nothing() :
    assert len(MojoHandicapper(None).sort_by_preference([], 'm', {})) == 0

def test_asserts_for_negative_value() :
    id_a = idlib.string_to_id('a')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body) :
        return -2
    h.add_handicapper(cfunc)
    try :
        h.sort_by_preference(counterparty_ids = [(id_a, None)], message_type = 'a message', message_body = {})
        return 0
    except AssertionError :
        return 1
    
def test_normal_operation() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 1
        else :
            return 0
    h.add_handicapper(cfunc)
    result = h.sort_by_preference(counterparty_ids = [(id_a, None), (id_b, None)], message_type = 'a message', message_body = {})
    assert len(result) == 2
    assert result[0][0] == id_b
    assert result[1][0] == id_a
    
def test_normal_operation_opposite_order() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 1
        else :
            return 0
    h.add_handicapper(cfunc)
    result = h.sort_by_preference(counterparty_ids = [(id_b, None), (id_a, None)], message_type = 'a message', message_body = {})
    assert len(result) == 2
    assert result[0][0] == id_b
    assert result[1][0] == id_a
    
def test_equal_handicap_returns_something() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        return 1
    h.add_handicapper(cfunc)
    result = h.sort_by_preference(counterparty_ids = [(id_a, None), (id_b, None)], message_type = 'a message', message_body = {})
    assert len(result) == 2
    assert result[0][0] != result[1]
    
def test_uses_first_handicapper_stored() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 1
        else :
            return 0
    h.add_handicapper(cfunc)
    def cfunc2(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 0
        else :
            return 2
    h.add_handicapper(cfunc2)
    result = h.sort_by_preference(counterparty_ids = [(id_b, None), (id_a, None)], message_type = 'a message', message_body = {})
    assert len(result) == 2
    assert result[0][0] == id_a
    assert result[1][0] == id_b
    
def test_uses_second_handicapper_stored() :
    id_a = idlib.string_to_id('a')
    id_b = idlib.string_to_id('b')
    h = MojoHandicapper()
    def cfunc(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 0
        else :
            return 2
    h.add_handicapper(cfunc)
    def cfunc2(counterparty_id, metainfo, message_type, message_body, id_a = id_a, id_b = id_b) :
        if counterparty_id == id_a :
            return 1
        else :
            return 0
    h.add_handicapper(cfunc2)
    result = h.sort_by_preference(counterparty_ids = [(id_b, None), (id_a, None)], message_type = 'a message', message_body = {})
    assert len(result) == 2
    assert result[0][0] == id_a
    assert result[1][0] == id_b


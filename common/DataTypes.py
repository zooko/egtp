#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

### standard modules
import types

### our modules
true = 1
false = 0
from MojoErrors import BadFormatError
import mojosixbit
import std

def NONEMPTY(thing, verbose):
    pass

def ANY(thing, verbose):
    if thing is None:
        raise BadFormatError, "any can't be none"

def STRING(thing, verbose, StringType=types.StringType):
    if type(thing) is not StringType:
        raise BadFormatError, "not a string"

def BOOLEAN(thing, verbose):
    if thing != 'true' and thing != 'false':
        raise BadFormatError, "not 'true' or 'false'"

def INTEGER(thing, verbose, StringType=types.StringType, IntType=types.IntType, LongType=types.LongType):
    if type(thing) not in (StringType, IntType, LongType,):
        raise BadFormatError, "not an integer (not a string, int or long)"

    if type(thing) is StringType:
        try:
            num = long(thing)
        except ValueError:
            raise BadFormatError, "not an integer"

        canonicalstr = `num`
        # remove any annoying python 1.5.2 Ls (1.6 doesn't do this)
        if canonicalstr[-1] == 'L':
            canonicalstr = canonicalstr[:-1]

        if canonicalstr != thing:
            raise BadFormatError, "not an integer (not canonical)"

        if long(canonicalstr) != num:
            raise BadFormatError, "not an integer (not canonical)"

def NON_NEGATIVE_INTEGER(thing, verbose, StringType=types.StringType, IntType=types.IntType, LongType=types.LongType):
    if type(thing) not in (StringType, IntType, LongType,):
        raise BadFormatError, "not an integer (not a string, int or long)"

    if type(thing) is not StringType:
        if thing < 0:
            raise BadFormatError, "not a non-negative integer (not non-negative)"
    else:
        try:
            num = long(thing)
        except ValueError:
            raise BadFormatError, "not an integer"

        canonicalstr = `num`
        # remove any annoying python 1.5.2 Ls (1.6 doesn't do this)
        if canonicalstr[-1] == 'L':
            canonicalstr = canonicalstr[:-1]

        if canonicalstr != thing:
            raise BadFormatError, "not an integer (not canonical)"

        if long(canonicalstr) != num:
            raise BadFormatError, "not an integer (not canonical)"

        if num < 0:
            raise BadFormatError, "not a non-negative integer (not non-negative)"

def ASCII_ARMORED_DATA(thing, verbose, StringType=types.StringType):
    if type(thing) is not types.StringType:
        raise BadFormatError, "not proper ascii-armored data - not a string"
    try:
        if not len(mojosixbit.a2b(thing)) > 0:
            raise BadFormatError, 'zero-length strings are rejected by ascii armored data match'
    except mojosixbit.Error, reason:
        raise BadFormatError, str(reason)
    ### !!!!! XXXXXX need to make this canonical!  --Zooko 2000-08-20

def UNIQUE_ID(thing, verbose, StringType=types.StringType):
    if type(thing) is not StringType or not std.is_sloppy_id(thing):
        raise BadFormatError, "not an unique id"

def ASCII_ID(thing, verbose, StringType=types.StringType):
    if type(thing) is not StringType or not std.is_mojosixbitencoded_id(thing):
        raise BadFormatError, "not an ascii id"

def MOD_VAL(thing, verbose, StringType=types.StringType):
    if type(thing) is not StringType:
        raise BadFormatError, "not proper modval - not a string"
    try:
        if not std.is_canonical_modval(mojosixbit.a2b(thing)):
            raise BadFormatError, "not a proper modval"
    except mojosixbit.Error:
        raise BadFormatError, "not a proper modval - not even proper ascii-encoded data"

def BINARY_SHA1(thing, verbose, StringType=types.StringType):
    if type(thing) is not StringType:
        raise BadFormatError, "not proper binary sha1 - not a string"
    if not std.is_canonical_uniq(thing):
        raise BadFormatError, "not a sha1 value - it does not have a length of 20" 

class OptionMarker :
    def __init__(self, template) :
        self.template = template
    def __repr__(self):
        return "OptionMarker: <%s>" % std.hr(self.template)

def AndMarker(templs):
    """
    Require the thing to match all templates.
    """
    def func(thing, verbose, templs = templs):
        for templ in templs:
            if verbose:
                inner_check_verbose(thing, templ)
            else:
                inner_check_noverbose(thing, templ)
    return func

def NotMarker(template):
    def func(thing, verbose, template = template):
        try:
            if verbose:
                inner_check_verbose(thing, template)
            else:
                inner_check_noverbose(thing, template)
        except BadFormatError:
            return
        raise BadFormatError, "got match when should not have"
    return func

NOT_PRESENT = OptionMarker(NotMarker(NONEMPTY))

def ListMarker(template, ListType=types.ListType, TupleType=types.TupleType):
    def func(thing, verbose, template = template, ListType=ListType, TupleType=TupleType):
        if type(thing) not in (ListType, TupleType,):
            raise BadFormatError, 'not a list'
        if verbose:
            try:
                i = 0
                while i < len(thing):
                    if verbose:
                        inner_check_verbose(thing[i], template)
                    else:
                        inner_check_noverbose(thing[i], template)
                    i = i + 1
            except BadFormatError, reason:
                raise BadFormatError, 'mismatch at index ' + std.hr(i) + ': ' + str(reason)
        else:
            for i in thing :
                if verbose:
                    inner_check_verbose(i, template)
                else:
                    inner_check_noverbose(i, template)
    return func

def is_template_matching(thing, templ):
    try:
        check_template(thing, templ)
    except BadFormatError:
        return false
    return true
       
def check_template(thing, templ):
    """
    throws BadFormatError if the thing does not match the template
    """
    try:
        inner_check_noverbose(thing, templ)
        return
    except BadFormatError, reason:
        pass
    try:
        inner_check_verbose(thing, templ)
    except BadFormatError, reason:
        raise BadFormatError, 'failed template check because: (' + str(reason) + ') template was: (' + std.hr(templ) + ') target was: (' + std.hr(thing) + ')'

def inner_check_verbose(thing, templ, FunctionType=types.FunctionType, MethodType=types.MethodType, DictType=types.DictType, StringType=types.StringType, LongType=types.LongType, IntType=types.IntType, ListType=types.ListType, TupleType=types.TupleType):
    # The following isn't really used right now, but I'm leaving the commented-out code for evidence.  --Zooko 2001-06-07
    # if isinstance(thing, mencode.PreEncodedThing):
    #     thing = thing.getvalue()

    templtype = type(templ)
    if templtype is FunctionType or templtype is MethodType:
        templ(thing, true)
    elif templtype is DictType:
        if not type(thing) is DictType:
            raise BadFormatError, 'target is not a dict'

        for key in templ.keys():
            if not thing.has_key(key):
                if not isinstance(templ[key], OptionMarker) :
                    raise BadFormatError, "lacks required key: (" + std.hr(key) + ")"
            else:
                try:
                    if isinstance(templ[key], OptionMarker) :
                        inner_check_verbose(thing[key], templ[key].template)
                    else :
                        inner_check_verbose(thing[key], templ[key])
                except BadFormatError, reason:
                    raise BadFormatError, 'mismatch in key (' + std.hr(key) + '): ' + str(reason)
    elif templtype is StringType:
        if type(thing) is not StringType:
            raise BadFormatError, "no match - target is not a string"
        if thing != templ:
            raise BadFormatError, "strings (" + thing + ') and (' + templ + ') do not match'
    elif templ == 0 or templ == -1 or templ == 1:
        if type(thing) is not LongType and type(thing) is not IntType:
            raise BadFormatError, 'expected int'
        if templ == 0:
            if thing < 0:
                raise BadFormatError, 'template called for non-negative value'
        elif templ == -1:
            return
        else:
            assert templ == 1
            if thing <= 0:
                raise BadFormatError, 'template called for strictly positive value'
    elif templtype is ListType or templtype is TupleType:
        failure_reason = 'did not match any of the ' + std.hr(len(templ)) + ' possible templates;'
        index = -1
        for i in templ:
            try:
                index = index + 1
                inner_check_verbose(thing, i)
                return
            except BadFormatError, reason:
                failure_reason = failure_reason + ' failed template' + std.hr(i) + ' at index ' + std.hr(index) + ' on thing ' + std.hr(thing) + ' because (' + str(reason) + ')'
        raise BadFormatError, failure_reason
    elif templ is None:
        if thing is not None:
            raise BadFormatError, 'expected None'
    else:
        assert false, "bad template - " + std.hr(templ)

def checkTemplate(thing, templ):
    """
    throws BadFormatError if the thing does not match the template

    @deprecated in favor of `check_template()' for naming consistency reasons
    """
    return check_template(thing, templ)

def inner_check_noverbose(thing, templ, FunctionType=types.FunctionType, MethodType=types.MethodType, DictType=types.DictType, StringType=types.StringType, LongType=types.LongType, IntType=types.IntType, ListType=types.ListType, TupleType=types.TupleType):
    # The following isn't really used right now, but I'm leaving the commented-out code for evidence.  --Zooko 2001-06-07
    # if isinstance(thing, mencode.PreEncodedThing):
    #     thing = thing.getvalue()

    templtype = type(templ)
    if templtype is FunctionType or templtype is MethodType:
        templ(thing, false)
    elif templtype is DictType:
        if not type(thing) is DictType:
            raise BadFormatError, 'target is not a dict'

        for key in templ.keys():
            if not thing.has_key(key):
                if not isinstance(templ[key], OptionMarker) :
                    raise BadFormatError, "lacks required key"
            else:
                if isinstance(templ[key], OptionMarker) :
                    inner_check_noverbose(thing[key], templ[key].template)
                else:
                    inner_check_noverbose(thing[key], templ[key])
    elif templtype is StringType:
        if type(thing) is not StringType:
            raise BadFormatError, "no match - target is not a string"
        if thing != templ:
            raise BadFormatError, "strings do not match"
    elif templ == 0 or templ == -1 or templ == 1:
        if type(thing) is not LongType and type(thing) is not IntType:
            raise BadFormatError, 'expected int'
        if templ == 0:
            if thing < 0:
                raise BadFormatError, 'template called for non-negative value'
        elif templ == -1:
            return
        else:
            assert templ == 1
            if thing <= 0:
                raise BadFormatError, 'template called for strictly positive value'
    elif templtype is ListType or templtype is TupleType:
        for i in templ:
            try:
                inner_check_noverbose(thing, i)
                return
            except BadFormatError:
                pass
        raise BadFormatError, "did not match any possible templates"
    elif templ is None:
        if thing is not None:
            raise BadFormatError, 'expected None'
    else:
        assert false, "bad template - " + std.hr(templ)

def test_not_on_rejection():
    check_template('a', NotMarker('b'))

def test_not_on_acceptance():
    try:
        check_template('a', NotMarker('a'))
        return 0
    except BadFormatError:
        return 1

def test_uses_function():
    spam = []
    check_template(3, lambda thing, verbose, spam = spam: spam.append(thing))
    assert len(spam) == 1 and spam[0] == 3

def test_none_passes_none():
    check_template(None, None)

def test_none_rejects_string():
    try:
        check_template('spam', None)
    except BadFormatError:
        return 1

def test_check_positive_accepts_positive():
    check_template(2, 1)

def test_check_positive_rejects_zero():
    try:
        check_template(0, 1)
    except BadFormatError:
        return 1
    
def test_check_positive_rejects_negative():
    try:
        check_template(-2, 1)
    except BadFormatError:
        return 1

def test_check_int_passes():
    check_template(3, -1)
    check_template(-2, -1)
    check_template(0, -1)

def test_check_int_fails_string():
    try:
        check_template('spam', -1)
    except BadFormatError:
        return 1    

def test_check_nonnegative_accepts_positive():
    check_template(2, 0)
    
def test_check_nonnegative_accepts_zero():
    check_template(0, 0)

def test_check_nonnegative_rejects_negative():
    try:
        check_template(-2, 0)
    except BadFormatError:
        return 1

# checks both items of a list passing
def test_check_list_pass() :
    template = ListMarker({"a" : ANY})
    thing = [{"a" : "a"},{"a" : "a"}]
    check_template(thing, template)

# checks the second item of a list failing
def test_check_list_fail() :
    template = ListMarker({"a" : ANY})
    thing = [{"a" : "a"},{"b" : "a"}]
    try :
        check_template(thing, template)
        return 0
    except BadFormatError :
        return 1

def test_check_option_accepts_nonexistent() :
    template = {'spam' : OptionMarker('eggs')}
    thing = {}
    check_template(thing, template)
    
def test_check_option_rejects_exists_with_none() :
    template = {'spam' : OptionMarker('eggs')}
    thing = {'spam' : None}
    try :
        check_template(thing, template)
    except BadFormatError :
        return 1
    
def test_check_option_accepts_valid() :
    template = {'spam' : OptionMarker('eggs')}
    thing = {'spam' : 'eggs'}
    check_template(thing, template)
    
def test_check_option_rejects_invalid() :
    template = {'spam' : OptionMarker('eggs')}
    thing = {'spam' : 'bacon'}
    try :
        check_template(thing, template)
    except BadFormatError :
        return 1

# checks formatting against a non-list
def test_check_bad_list() :
    template = ListMarker({"a" : ANY})
    thing = 'spam'
    try :
        check_template(thing, template)
        return 0
    except BadFormatError :
        return 1

# use list of matches none of which match (although combined pieces do)
def test_check_multiple_fail() :
    template = (
        {"a" : ANY, "b" : ANY},
        {"c" : ANY, "d" : ANY}
        )
    thing = {"a" : "spam", "c" : "eggs"}
    try :
        check_template(thing, template)
        return 0
    except BadFormatError :
        pass
    
# use list of templates the first of which matches
def test_check_multiple_pass_first() :
    template = (
        {"a" : ANY, "b" : ANY},
        {"c" : ANY, "d" : ANY}
        )
    thing = {"a" : "spam", "b" : "eggs"}
    try :
        check_template(thing, template)
        return
    except BadFormatError :
        return 0
    
# use list of two templates the second of which matches
def test_check_multiple_pass_second() :
    template = (
        {"a" : ANY, "b" : ANY},
        {"c" : ANY, "d" : ANY}
        )
    thing = {"c" : "spam", "d" : "eggs"}
    try :
        check_template(thing, template)
        return
    except BadFormatError :
        return 0
    
# doesn't match first depth but does second
def test_check_multiple_in_second_depth_pass() :
    template = {"a" : ({"c" : ANY}, {"d" : ANY})}
    thing = {"a" : {"d" : "spam"}}
    try :
        check_template(thing, template)
        return
    except BadFormatError :
        return 0
    
# matches first depth but not second
def test_check_multiple_in_second_depth_fail() :
    template = {"a" : ({"c" : ANY}, {"d" : ANY})}
    thing = {"a" : {"a" : "spam"}}
    try :
        check_template(thing, template)
        return 0
    except BadFormatError :
        return 1
    
mojo_test_flag = 1

def run():
    import RunTests
    RunTests.runTests(["DataTypes"])

if __name__ == '__main__':
    run()


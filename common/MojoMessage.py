#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import string
import types

# pyutil modules
from config import DEBUG_MODE
from debugprint import debugprint
import humanreadable

# our modules
import Cache
from DataTypes import BadFormatError, ANY, STRING, UNIQUE_ID, checkTemplate, OptionMarker, NON_NEGATIVE_INTEGER
from MojoErrors import MojoMessageError
import idlib
import mencode


# Generate messages with the following Mojo version number.
CURRENT_MOJO_VER=0.9991

# Accept messages of the following version number or later.
MIN_MOJO_VER=0.99

# Reject messages of the following version number or later.
NEXT_MOJO_VER=2.0


# Note that we initialize `templs' in "OurMessages.py".
import OurMessages


class IncompatibleVersionError(MojoMessageError):
    pass

class InternalError(MojoMessageError):
    pass

class WrongMessageTypeError(MojoMessageError):
    pass

class UnknownMessageTypeError(MojoMessageError):
    """
    `MojoMessage.templs' does not contain a template for checking messages of this type.
    """
    pass



# These functions that take a message in string form as their argument will throw an
# IncompatibleVersionError if the message doesn't have a good version number.

# The rule is that any message whose `protocol' major version number is "Mojo v1.xx" should be
# usable by any Mojo v1 capable application.  If you extend the Mojo protocol in a
# backwards-compatible way (i.e. a pre-existing Mojo application can interoperate with your Mojo
# application) then you can change the minor version number.  This allows an application that is
# aware of your extension to use it and an application that is not aware of your extension but
# does Mojo v1 to continue to interoperate.  If you change the Mojo protocol in a
# non-backwards-compatible way you should change the major version number.

# A correct Mojo v1 application will reject out of hand messages with a different major version
# number.

# A correct Mojo v1 application will also treat _all_ messages with maximal suspicion even if
# they have a compatible version number -- after all we cannot trust our interlocutors to tell
# the truth!



# We're pretty mono-threaded.  A low number is fine as most calls to MojoMessage functions will be
# sequential calls using the same msgString.  This cache is intended to speed up the common case
# of sequential calls to MojoMessage.getSPAM with the same msgString.
# XXX NOTE: Cache() doesn't do well if given a maxsize and an item > maxsize bytes is inserted;
#           don't make these size based caches
_MAX_MEMOIZE_CACHE_ITEMS = 2
# used to memoize our mdecode(msgString) results
global _internal_msgString_mdecode_cache
_internal_msgString_mdecode_cache = None
# used to memoize __internal_checkMsg(msgString) successes
global _internal_checkMsg_cache
_internal_checkMsg_cache = None

def init():
    global _internal_msgString_mdecode_cache 
    _internal_msgString_mdecode_cache = Cache.CacheSingleThreaded(maxitems=_MAX_MEMOIZE_CACHE_ITEMS)
    global _internal_checkMsg_cache
    _internal_checkMsg_cache = Cache.CacheSingleThreaded(maxitems=_MAX_MEMOIZE_CACHE_ITEMS)

def shutdown():
    global _internal_msgString_mdecode_cache 
    _internal_msgString_mdecode_cache = None
    global _internal_checkMsg_cache
    _internal_checkMsg_cache = None

def __internal_mdecode_nocache(msgString):
    try:
        return mencode.mdecode(msgString)
    except mencode.MencodeError, le:
        if DEBUG_MODE:
            raise MojoMessageError, (msgString, le,)
        else:
            raise MojoMessageError, le

def __internal_mdecode_cache(msgString) :
    """
    This memoizes our calls to mdecode since it is being called repeatedly on all messages for
    each getFoo and checkMsg function below.
    """
    decodedmsg = _internal_msgString_mdecode_cache.get(msgString)
    if decodedmsg is None :
        try:
            decodedmsg = __internal_mdecode_nocache(msgString)
        except MojoMessageError, le:
            raise MojoMessageError, (msgString, le,)

        # store the decoded representation in our cache, accounting
        # for both the size of the key and value in itemsize
        _internal_msgString_mdecode_cache.insert(msgString, decodedmsg)
    return decodedmsg


def getType(msgString):
    """
    @param msgString the string containing the message in canonical form

    @throws BadFormatError if `msgString' is badly formed or of an incompatible version of the
        Mojo protocol

    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString)['header']['message type']


def getRecipient(msgString):
    """
    @param msgString the string containing the message in canonical form

    @return the recipient of the message or `None' if not included
  
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString)['header'].get('recipient')

def getSendersMetaInfo(msgString):
    """
    @param msgString the string containing the message in canonical form
    @return the meta info included with the message or None if not included
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString).get('metainfo', None)

def getExtraMetaInfo(msgString):
    """
    @param msgString the string containing the message in canonical form
    @return the meta info included with the message or None if not included
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString).get('extra_metainfo', None)

def getBody(msgString):
    """
    @param msgString the string containing the message in canonical form
    @return the body of the message excluding header info
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString).get('message body')


def getReference(msgString):
    """
    @param msgString the string containing the message in canonical form
    @return the reference of the message or `None' if this is an initial message
    @postcondition Result is of correct form.: idlib.is_sloppy_id(result)
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString)['header'].get('reference')


def getNonce(msgString):
    """
    @param msgString the string containing the message in canonical form
    @return the nonce of the initiating message or `None' if this is a response message
    @postcondition Result is of correct form.: idlib.is_sloppy_id(result)
    @memoizable
    """
    __internal_checkMsg(msgString)
    return __internal_mdecode_cache(msgString)['header'].get('nonce')


def makeInitialMessage(msgtype, msgbody, recipient_id, nonce, freshnessproof, mymetainfo=None):
    """
    @param msgtype the type of the message, human readable string
    @param msgbody an Mojo dict containing the contents of the message
    @recipient_id the id of the intended recipient
    @param nonce a unique 20-byte number to ensure uniqueness of the message
    @param freshnessproof the binary hash of the most recent message that you've received
        from this counterparty, to ensure freshness
    @param mymetainfo is optional and should contain the senders most recent
        meta info if they wish to include it with their message.

    @return the canonical string representation of this Mojo message

    @memoizable

    @precondition `recipient_id' must be an id.: idlib.is_sloppy_id(recipient_id): "recipient_id: %s" % humanreadable.hr(recipient_id)
    @precondition `nonce' must be an id.: idlib.is_sloppy_id(nonce): "nonce: %s" % humanreadable.hr(nonce)
    @precondition `freshnessproof' must be `None' or a binary id.: (freshnessproof is None) or (idlib.is_binary_id(freshnessproof, 'msg')): "freshnessproof: %s" % humanreadable.hr(freshnessproof)
    """
    assert idlib.is_sloppy_id(recipient_id), "precondition: `recipient_id' must be an id." + " -- " + "recipient_id: %s" % humanreadable.hr(recipient_id)
    assert idlib.is_sloppy_id(nonce), "precondition: `nonce' must be an id." + " -- " + "nonce: %s" % humanreadable.hr(nonce)
    assert (freshnessproof is None) or (idlib.is_binary_id(freshnessproof, 'msg')), "precondition: `freshnessproof' must be `None' or a binary id." + " -- " + "freshnessproof: %s" % humanreadable.hr(freshnessproof)

    recipient_id = idlib.sloppy_id_to_bare_binary_id(recipient_id)
    nonce = idlib.sloppy_id_to_bare_binary_id(nonce)

    msgdict = {'header': {'protocol': 'Mojo v'+str(CURRENT_MOJO_VER), 'message type': msgtype, 'recipient': recipient_id, 'nonce': nonce}}

    if freshnessproof is not None:
        msgdict['header']['freshness proof'] = idlib.canonicalize(freshnessproof)

    if msgbody:
        msgdict['message body'] = msgbody
    
    if mymetainfo:
        msgdict['metainfo'] = mymetainfo

    msgString = mencode.mencode(msgdict)

    if DEBUG_MODE:
        # First it has to match the basic template for all Mojo Messages.
        try:
            # Why do we do this instead of just using the msgdict as passed in above?
            # In order to get to the contents of a PreEncodedThing.  Remember this is
            # just for DEBUG_MODE.  --Zooko 2001-06-07
            msgdict = __internal_mdecode_nocache(msgString)

            checkTemplate(msgdict, BASE_TEMPL)

            __internal_checkMsgBody(msgdict)
            __internal_checkMojoVersion(msgdict)
            __internal_checkMsgType(msgdict)
        except (BadFormatError, TypeError), le:
            raise BadFormatError, (msgdict, le,)

    return msgString

def makeResponseMessage(msgtype, msgbody, reference, freshnessproof, mymetainfo=None, extrametainfo=None):
    """
    @param msgtype the type of the message, human readable string
    @param msgbody an Mojo dict containing the contents of the message
    @param reference the secure hash of the canonical string representation of the previous
        message to which this is a response
    @param freshnessproof the binary hash of the most recent message that you've received
        from this counterparty, to ensure freshness, or `None' if none
    @param mymetainfo is optional and should contain the senders most recent
        meta info if they wish to include it with their message.  (or a mencode.PreEncodedThing of the info)
    @param extrametainfo is optional and should contain a list of a few other counterparties
        metainfo dicts to share.  (or a mencode.PreEncodedThing of the info list)

    @return the canonical string representation of this Mojo message

    @memoizable

    @precondition `reference' must be an id.: idlib.is_sloppy_id(reference): "reference: %s" % humanreadable.hr(reference)
    @precondition `freshnessproof' must be None or an id.: (freshnessproof is None) or idlib.is_sloppy_id(freshnessproof, 'msg'): "freshnessproof: %s" % humanreadable.hr(freshnessproof)
    """
    assert idlib.is_sloppy_id(reference), "precondition: `reference' must be an id." + " -- " + "reference: %s" % humanreadable.hr(reference)
    assert (freshnessproof is None) or idlib.is_sloppy_id(freshnessproof, 'msg'), "precondition: `freshnessproof' must be None or an id." + " -- " + "freshnessproof: %s" % humanreadable.hr(freshnessproof)

    if freshnessproof is not None:
        freshnessproof = idlib.canonicalize(freshnessproof)

    msgdict = {'header': {'protocol': 'Mojo v'+str(CURRENT_MOJO_VER), 'message type': msgtype, 'reference': reference, 'freshness proof': freshnessproof}}

    if msgbody:
        msgdict['message body'] = msgbody

    if mymetainfo:
        msgdict['metainfo'] = mymetainfo

    if extrametainfo:
        msgdict['extra_metainfo'] = extrametainfo

    msgString = mencode.mencode(msgdict)

    if DEBUG_MODE:
        # First it has to match the basic template for all Mojo Messages.
        try:
            # Why do we do this instead of just using the msgdict as passed in above?
            # In order to get to the contents of a PreEncodedThing.  Remember this is
            # just for DEBUG_MODE.  --Zooko 2001-06-07
            msgdict = __internal_mdecode_nocache(msgString)

            checkTemplate(msgdict, BASE_TEMPL)

            __internal_checkMsgBody(msgdict)
            __internal_checkMojoVersion(msgdict)
            __internal_checkMsgType(msgdict)
        except (BadFormatError, TypeError), le:
            raise BadFormatError, (msgdict, le,)

    return msgString

BASE_TEMPL = {
    'header': {
        'protocol': STRING,
        'message type': STRING,
        },
    'metainfo': OptionMarker(ANY),  # metainfo is throughly template checked as it gets processed, not automatically as it should never cause the message to fail completely
    }


INITIAL_TEMPL = {
    'header': {
        'protocol': STRING,
        'message type': STRING,
        'recipient': UNIQUE_ID,
        'nonce': UNIQUE_ID,
        },
    'metainfo': OptionMarker(ANY),
    }


RESPONSE_TEMPL = {
    'header': {
        'protocol': STRING,
        'message type': STRING,
        'reference': UNIQUE_ID,
        },
    'metainfo': OptionMarker(ANY),
    }

def checkMessageType(msgString, requiredmsgtype):
    """
    @param msgString the string containing the message in canonical form
    @param requiredmsgtype the required type of the message in a human readable string or `None'
        if any type is acceptable

    @throws WrongMessageTypeError if `requiredmsgtype' is not `None' and `msgString' is not of
        `requiredmsgtype'

    @memoizable
    """
    __internal_checkMsgType(__internal_mdecode_cache(msgString), requiredmsgtype)


def __internal_checkMsgType(msgdict, requiredmsgtype = None):
    """
    @memoizable
    """
    if requiredmsgtype:
        if requiredmsgtype != msgdict['header']['message type']:
            raise WrongMessageTypeError


def __internal_checkMsg(msgString, requiredmsgtype = None):
    """
    @memoizable
    """
    # return if this msgString has already passed its checks
    if _internal_checkMsg_cache.get(msgString) :
        return
    
    msgdict = __internal_mdecode_cache(msgString)

    # First it has to match the basic template for all Mojo Messages.
    try:
        checkTemplate(msgdict, BASE_TEMPL)

        __internal_checkMsgBody(msgdict)
        __internal_checkMojoVersion(msgdict)
        __internal_checkMsgType(msgdict, requiredmsgtype)
    except (BadFormatError, TypeError), le:
        raise BadFormatError, (msgdict, requiredmsgtype, le,)

    # memoize the fact that this msgdict passed the checks
    _internal_checkMsg_cache.insert(msgString, 1)

def __internal_checkMsgBody(msgdict):
    """
    @memoizable
    """
    # Either the message has a mojo header indicating failure, or it matches the template for its specific conversation type.
    templ = OurMessages.templs.get(msgdict['header']['message type'])

    if templ is None:
        debugprint('NOTE: untemplated message of type %s\n', args=(msgdict['header']['message type'],), v=3, vs='MojoMessage')
        return
    checkTemplate(msgdict.get('message body'), {
            'mojo message': OptionMarker(templ),
            'mojo header': OptionMarker(OurMessages.MOJO_HEADER_TEMPL)
            })

def __internal_checkMojoVersion(msgdict, minVer=MIN_MOJO_VER, nextVer=NEXT_MOJO_VER):
    """
    @param msgString the string containing the message in canonical form
    @param minVer we don't accept messages of less than this version number
    @param nextVer we don't accept messages of a this version number or greater

    @throws IncompatibleVersionError if `eDict' is of an incompatible version of the Mojo 
        protocol

    @memoizable
    """
    vN = __internal_getMojoVersion(msgdict)

    if (vN < minVer) or (vN >= nextVer):
        raise IncompatibleVersionError


def __internal_getMojoVersion(msgdict):
    """
    @memoizable
    """
    protStr = msgdict['header']['protocol']

    if protStr[0:6] != "Mojo v":
        raise BadFormatError, "not a Mojo protocol message"

    verNum = string.atof(protStr[6:])
    # print "protStr[6:] " + protStr[6:] + ", verNum " + `verNum` # DEBUGPRINT

    return verNum


mojo_test_flag = 1


def run():
    import RunTests
    RunTests.runTests(["MojoMessage"])
    pass


#### this runs if you import this module by itself
if __name__ == '__main__':
    run()


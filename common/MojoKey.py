#!/usr/bin/env python
#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

### standard modules
import re

### our modules
from DataTypes import ANY, MOD_VAL, NON_NEGATIVE_INTEGER, UNIQUE_ID, ASCII_ARMORED_DATA
import OurMessages
true = 1
false = 0
import MojoMessage
import idlib
import mencode
import modval
import mojosixbit
import mojoutil
import randsource


def pubkey_to_id(key):
    """
    @precondition `key' is a public key in SEXP form.: publicKeyIsWellFormed(key): "key: %s" % hr(key)
    """
    assert publicKeyIsWellFormed(key), "`key' is a public key in SEXP form." + " -- " + "key: %s" % hr(key)

    if publicKeyForVerifyingTokenSignaturesIsWellFormed(key):
        return idlib.make_id(key, thingtype='token verifying public key')
    elif publicKeyForCommunicationSecurityIsWellFormed(key):
        return idlib.make_id(key, thingtype='comms public key')
    else:
        return idlib.make_id(key, thingtype='public key')

#  This file is licensed under the
def getModulusFromPublicKey(key) :
    dict = mencode.mdecode(key)
    return mojosixbit.a2b(dict['key values']['public modulus'])

def makePublicRSAKeyForVerifyingTokenSignatures(keyMV):
    """
    @param keyMV the key in a modval instance

    @return the Mojo encoding of the key
    """
    return mencode.mencode({ 'key header': { 'type': "public", 'cryptosystem': "RSA", 'usage': "only for verifying token signatures", 'value of signed token': { 'currency': "Mojo Test Points", 'amount': "16" } }, 'key values': { 'public modulus': mojosixbit.b2a(keyMV.get_modulus()), 'public exponent': repr(keyMV.get_exponent()) }})


def makePublicRSAKeyForCommunicating(keyMV):
    return mencode.mencode({ 'key header': { 'type': "public", 'cryptosystem': "RSA", 'usage': "only for communication security" }, 'key values': { 'public modulus': mojosixbit.b2a(keyMV.get_modulus()), 'public exponent': repr(keyMV.get_exponent()) }})

   
def makeRSAPublicKeyMVFromSexpString(keySexpStr):
    """
    @param keySexpStr RSA public key in MojoMessage format

    @return modval instance containing the modulus and exponent of `keySexpStr'

    @precondition `keySexpStr' is well-formed RSA public key.: publicRSAKeyIsWellFormed(keySexpStr): "keySexpStr: %s" % hr(keySexpStr)
    @precondition `keySexpStr' is sane.: publicRSAKeyIsSane(keySexpStr): "keySexpStr: %s" % hr(keySexpStr)
    """
    assert publicRSAKeyIsWellFormed(keySexpStr), "`keySexpStr' is well-formed RSA public key." + " -- " + "keySexpStr: %s" % hr(keySexpStr)
    assert publicRSAKeyIsSane(keySexpStr), "`keySexpStr' is sane." + " -- " + "keySexpStr: %s" % hr(keySexpStr)

    ed = mencode.mdecode(keySexpStr)

    return modval.new(mojosixbit.a2b(ed['key values']['public modulus']), long(ed['key values']['public exponent']))


def publicRSAKeyIsSane(keySexpStr):
    """
    @param keySexpStr public key (in an s-expression string with accompanying meta-data)

    @return `true' if and only if `keySexpStr' is a correctly formed MojoMessage of an RSA public key for verifying token signatures which also satisfies a few mathematical sanity checks

    @precondition `keySexpStr' is well-formed.: publicRSAKeyIsWellFormed(keySexpStr): "keySexpStr: %s" % hr(keySexpStr)
    """
    assert publicRSAKeyIsWellFormed(keySexpStr), "`keySexpStr' is well-formed." + " -- " + "keySexpStr: %s" % hr(keySexpStr)

    ed = mencode.mdecode(keySexpStr)

    keyMV = modval.new(mojosixbit.a2b(ed['key values']['public modulus']), long(ed['key values']['public exponent']))
       
    return modval.verify_key(keyMV.get_modulus()) == None


def keyIsWellFormed(keySexpStr):
    """
    @param keySexpStr key in an s-expression string with accompanying meta-data

    @return `true' if and only if `keySexpStr' is in the correct format for keys in the Mojo system
    """
    try:
        ed = mencode.mdecode(keySexpStr)

        MojoMessage.checkTemplate(ed, K_TEMPL)
    except (MojoMessage.BadFormatError, MojoMessage.WrongMessageTypeError, KeyError, mojosixbit.Error, mencode.MencodeError), x:
        return false

    return true

K_TEMPL={'key header': {'cryptosystem': ANY, 'type': ANY, 'usage': ANY}, 'key values': {}}


def publicKeyIsWellFormed(keySexpStr):
    """
    @param keySexpStr key in an s-expression string with accompanying meta-data

    @return `true' if and only if `keySexpStr' is in the correct format for keys in the Mojo system
    """
    if not keyIsWellFormed(keySexpStr):
        return false

    try:
        ed = mencode.mdecode(keySexpStr)

        MojoMessage.checkTemplate(ed, PK_TEMPL)
    except (MojoMessage.BadFormatError, MojoMessage.WrongMessageTypeError, KeyError, mojosixbit.Error, mencode.MencodeError):
        return false

    return true

PK_TEMPL={'key header': {'cryptosystem': ANY, 'type': "public", 'usage': ANY}, 'key values': {}}


def publicRSAKeyIsWellFormed(keySexpStr):
    """
    @param keySexpStr public RSA key in an s-expression string with accompanying meta-data

    @return tuple of (`true' if and only if `keySexpStr' is in the correct format for public RSA keys in the Mojo system, the key data in sexp format)
    """
    if not publicKeyIsWellFormed(keySexpStr):
        return false

    try:
        ed = mencode.mdecode(keySexpStr)

        MojoMessage.checkTemplate(ed, PK_TEMPL)
    except (MojoMessage.BadFormatError, MojoMessage.WrongMessageTypeError, KeyError, mojosixbit.Error):
        return false

    return true

PRK_TEMPL={'key header': {'cryptosystem': "RSA", 'type': "public", 'usage': ANY}, 'key values': {'public modulus': MOD_VAL, 'public exponent': NON_NEGATIVE_INTEGER}}


def publicKeyForVerifyingTokenSignaturesIsWellFormed(keySexpStr):
    """
    @param keySexpStr public key for verifying token signatures in an s-expression string with accompanying meta-data

    @return `true' if and only if `keySexpStr' is in the correct format for public keys which are used for token signing in the Mojo system
    """
    if not publicKeyIsWellFormed(keySexpStr):
        return false

    try:
        ed = mencode.mdecode(keySexpStr)

        MojoMessage.checkTemplate(ed, PKFVTS_TEMPL)
    except (MojoMessage.BadFormatError, MojoMessage.WrongMessageTypeError, KeyError, mojosixbit.Error, mencode.MencodeError):
        return false

    return true

PKFVTS_TEMPL={'key header': {'cryptosystem': ANY, 'type': "public", 'usage': "only for verifying token signatures", 'value of signed token': {'currency': ANY, 'amount': NON_NEGATIVE_INTEGER}}, 'key values': {}}


def publicKeyForCommunicationSecurityIsWellFormed(keySexpStr):
    """
    @param keySexpStr public key for verifying token signatures in an s-expression string with accompanying meta-data

    @return `true' if and only if `keySexpStr' is in the correct format for public keys which are used for communication security
    """
    if not publicKeyIsWellFormed(keySexpStr):
        return false

    try:
        ed = mencode.mdecode(keySexpStr)

        MojoMessage.checkTemplate(ed, OurMessages.PKFC_TEMPL)
    except (MojoMessage.BadFormatError, MojoMessage.WrongMessageTypeError, KeyError, mojosixbit.Error, mencode.MencodeError), x:
        return false

    return true


def publicRSAKeyForVerifyingTokenSignaturesIsWellFormed(key):
    """
    @param key public RSA key for verifying token signatures in an s-expression string with accompanying meta-data

    @return `true' if and only if `key' is in the correct format for public keys which are used for token signing in the Mojo system
    """
    if (publicRSAKeyIsWellFormed(key)) and (publicKeyForVerifyingTokenSignaturesIsWellFormed(key)):
        return true
    else:
        return false


def publicRSAKeyForCommunicationSecurityIsWellFormed(key):
    """
    @param key public RSA key for communications security in an s-expression string with accompanying meta-data

    @return `true' if and only if `key' is in the correct format for public keys which are used for communications security
    """
    if (publicRSAKeyIsWellFormed(key)) and (publicKeyForCommunicationSecurityIsWellFormed(key)):
        return true
    else:
        return false


def getDenomination(keySexpStr):
    """
    Get the currency and value of tokens verified by this public key.

    @param key public RSA key for verifying token signatures in an s-expression string with accompanying meta-data

    @return a tuple of (currency, amount), where `currency' is a string and `amount' is a long

    @precondition `keySexpStr' is well-formed.: publicKeyForVerifyingTokenSignaturesIsWellFormed(key): "keySexpStr: %s" % hr(keySexpStr)
    """
    assert publicKeyForVerifyingTokenSignaturesIsWellFormed(key), "`keySexpStr' is well-formed." + " -- " + "keySexpStr: %s" % hr(keySexpStr)

    ed = mencode.mdecode(keySexpStr)

    return (ed['key header']['value of signed token']['currency'], long(ed['key header']['value of signed token']['amount']))


def test_publicKeyIsWellFormed():
    assert publicKeyIsWellFormed(_sample_RSA_public_key_for_verifying_token_signatures_string)
    pass


def test_publicKeyIsWellFormed_mustRejectRandomJunk():
    assert not publicKeyIsWellFormed("fooey")
    
    
def test_publicKeyIsWellFormed_mustRejectPrivateKey():
    assert not publicKeyIsWellFormed(_sample_RSA_private_key_for_signing_tokens_message)
    pass


def test_publicKeyIsWellFormed_mustRejectIllFormedKey():
    print 'XXX write test_publicKeyIsWellFormed_mustRejectIllFormedKey'
 
def test_publicRSAKeyIsWellFormed():
    assert publicRSAKeyIsWellFormed(_sample_RSA_public_key_for_verifying_token_signatures_string)
    pass

    
def test_publicRSAKeyIsWellFormed_mustRejectRSAPrivateKey():
    assert not publicRSAKeyIsWellFormed(_sample_RSA_private_key_for_signing_tokens_message)
    pass

    
def test_publicRSAKeyIsWellFormed_mustRejectRandomJunk():
    assert not publicRSAKeyIsWellFormed("whatever")


def test_publicRSAKeyIsWellFormed_mustReject3DESSecretKey():
    assert not publicRSAKeyIsWellFormed(_sample_3DES_secret_key_message)
    pass


def test_publicKeyForVerifyingTokenSignaturesIsWellFormed():
    assert publicKeyForVerifyingTokenSignaturesIsWellFormed(_sample_RSA_public_key_for_verifying_token_signatures_string)
    pass


def test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectPrivateKey():
    assert not publicKeyForVerifyingTokenSignaturesIsWellFormed(_sample_RSA_private_key_for_signing_tokens_message)
    pass


def test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectBadUsage():
    print 'XXX write test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectBadUsage'

def test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectIllFormed():
    print 'XXX unwritten test!'

def test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectIllFormed_2():
    print 'XXX unwritten test!'

def test_publicKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectIllFormed_3():
    print 'XXX unwritten test!'

def test_publicRSAKeyForVerifyingTokenSignaturesIsWellFormed():
    assert publicRSAKeyForVerifyingTokenSignaturesIsWellFormed(_sample_RSA_public_key_for_verifying_token_signatures_string)
    pass


def test_publicRSAKeyForVerifyingTokenSignaturesIsWellFormed_mustRejectPrivateKey():
    assert not publicRSAKeyForVerifyingTokenSignaturesIsWellFormed(_sample_RSA_private_key_for_signing_tokens_message)
    pass


def test_keyIsWellFormed():
    assert keyIsWellFormed(_sample_RSA_public_key_for_verifying_token_signatures_string)
    pass


def disabled_test_keyIsWellFormed_2():
    assert keyIsWellFormed(_sample_RSA_private_key_for_signing_tokens_message)
    pass


def disabled_test_keyIsWellFormed_3():
    assert keyIsWellFormed(_sample_3DES_secret_key_message)
    pass


def test_keyIsWellFormed_mustRejectIllFormed():
    assert not keyIsWellFormed("")


def test_keyIsWellFormed_mustRejectIllFormed_2():
    print 'XXX unwritten test!'

def test_keyIsWellFormed_mustRejectIllFormed_3():
    print 'XXX unwritten test!'

def test_keyIsWellFormed_mustRejectIllFormed_4():
    print 'XXX unwritten test!'

def test_keyIsWellFormed_mustRejectIllFormed_5():
    print 'XXX unwritten test!'

def test_keyIsWellFormed_mustRejectIllFormed_5():
    print 'XXX unwritten test!'
 
def test_makePublicRSAKeyForVerifyingTokenSignatures():
    kMV = modval.new(sampleModulus, sampleExponent)

    kSEXP = makePublicRSAKeyForVerifyingTokenSignatures(kMV)

    assert publicRSAKeyForVerifyingTokenSignaturesIsWellFormed(kSEXP)

    pass


def test_makeRSAPublicKeyMVFromSexpString():
    kMV = makeRSAPublicKeyMVFromSexpString(_sample_RSA_public_key_for_verifying_token_signatures_string)

    assert kMV.get_exponent() == sampleExponent 
    assert kMV.get_modulus() == sampleModulus 
    pass


def test_publicRSAKeyIsSane():
    import randsource
    import modval

    kMV = modval.new_random(10, 3)

    sxpStr = makePublicRSAKeyForVerifyingTokenSignatures(kMV)

    assert publicRSAKeyIsSane(sxpStr)

    pass



sampleModulus = mojosixbit.a2b('pOqDTHSy6UItPw')
sampleExponent = 3


# sample RSA public key message (note: this is _NOT_ in canonical form -- I added extraneous carriage returns and indentation to aid readability.  Delete all carriage returns and whitespace indentation to get canonical form, as shown below):
#(
#     (10:key header
#         (
#             (12:cryptosystem3:RSA)
#             (4:type6:public)
#             (5:usage35:only for verifying token signatures)
#             (21:value of signed token
#                 (
#                     (6:amount2:16)
#                     (8:currency16:Mojo Test Points)))))
#     (10:key values
#         (
#             (15:public exponent1:3)
#             (14:public modulus14:pOqDTHSy6UItPw))))

# sample RSA public key message in canonical form

_sample_RSA_public_key_for_verifying_token_signatures_string='(4:dict(6:string10:key header)(4:dict(6:string12:cryptosystem)(6:string3:RSA)(6:string4:type)(6:string6:public)(6:string5:usage)(6:string35:only for verifying token signatures)(6:string21:value of signed token)(4:dict(6:string6:amount)(6:string2:16)(6:string8:currency)(6:string16:Mojo Test Points)))(6:string10:key values)(4:dict(6:string15:public exponent)(6:string1:3)(6:string14:public modulus)(6:string14:pOqDTHSy6UItPw)))'

# {
#     'key header': {
#         'type': 'public',
#         'cryptosystem': 'RSA',
#         'usage': 'only for verifying token signatures',
#         'value of signed token': {
#         'currency': 'Mojo Test Points',
#         'amount': '16',
#     },
#     'key values': {
#         'public modulus': 'pOqDTHSy6UItPw',
#         'public exponent': '3',
#     },
# },

_sample_RSA_public_key_for_verifying_token_signatures_edict = { 'header': { 'protocol': 'Mojo v0.94', 'message type': 'key' }, 'key': { 'key header': { 'type': 'public', 'cryptosystem': 'RSA', 'usage': 'only for verifying token signatures', 'value of signed token': { 'currency': 'Mojo Test Points', 'amount': '16' } }, 'key values': { 'public modulus':'pOqDTHSy6UItPw', 'public exponent': '3' } } }


# sample private RSA key message (note: this is _NOT_ in canonical form -- I added extraneous carriage returns and indentation to aid readability.  Delete all carriage returns and whitespace indentation to get canonical form, as shown below):
#    (
#        (6:header
#            (
#                (8:protocol10:Mojo v0.94)
#                (12:message type3:key)))
#        (3:key
#            (
#                (10:key header
#                    (
#                        (4:type7:private)
#                        (12:cryptosystem3:RSA)
#                        (5:usage23:only for signing tokens)
#                        (21:value of signed token
#                            (
#                                (8:currency16:Mojo Test Points)
#                                (6:amount2:16)))))
#                (10:key values
#                    (
#                        (16:private exponent128:PRIVATE_EXPONENT_BITS...........................................................................................................)
#                        (15:private factors
#                            (
#                                (1:p64:PRIVATE_FACTOR_P_BITS...........................................)
#                                (1:q64:PRIVATE_FACTOR_Q_BITS...........................................))))))))

# sample private RSA key message in canonical form:
_sample_RSA_private_key_for_signing_tokens_message='(4:dict(6:string6:header)(4:dict(6:string12:message type)(6:string3:key)(6:string8:protocol)(6:string10:Mojo v0.94))(6:string3:key)(4:dict(6:string10:key header)(4:dict(6:string12:cryptosystem)(6:string3:RSA)(6:string4:type)(6:string7:private)(6:string5:usage)(6:string23:only for signing tokens)(6:string21:value of signed token)(4:dict(6:string6:amount)(6:string2:16)(6:string8:currency)(6:string16:Mojo Test Points)))(6:string10:key values)(4:dict(6:string16:private exponent)(6:string128:PRIVATE_EXPONENT_BITS...........................................................................................................)(6:string15:private factors)(4:dict(6:string1:p)(6:string64:PRIVATE_FACTOR_P_BITS...........................................)(6:string1:q)(6:string64:PRIVATE_FACTOR_Q_BITS...........................................)))))'

# sample withdrawal message (note: this is _NOT_ in canonical form -- I added extraneous carriage returns and indentation to aid readability.  Delete all carriage returns and whitespace indentation to get canonical form, as shown below):
#    (
#        (6:header
#            (
#                (8:protocol10:Mojo v0.94)
#                (12:message type16:token withdrawal)))
#        (21:token ids for signing
#            (
#                (23:token id for signing #120:TOKEN_ID_4_S_BITS_1.)
#                (23:token id for signing #220:TOKEN_ID_4_S_BITS_2.)
#                (23:token id for signing #320:TOKEN_ID_4_S_BITS_3.))))

# sample withdrawal message in canonical form:
_sample_withdrawal_message='(4:dict(6:string6:header)(4:dict(6:string12:message type)(6:string16:token withdrawal)(6:string8:protocol)(6:string10:Mojo v0.94))(6:string21:token ids for signing)(4:dict(6:string23:token id for signing #1)(6:string20:TOKEN_ID_4_S_BITS_1.)(6:string23:token id for signing #2)(6:string20:TOKEN_ID_4_S_BITS_2.)(6:string23:token id for signing #3)(6:string20:TOKEN_ID_4_S_BITS_3.)))'

_sample_withdrawal_reply_message_edict={'header': {'protocol': 'Mojo v0.94', 'message type': 'token withdrawal reply'}, 'signed token ids for signing': {'signed token id for signing #1': 'S_T_ID_4_S_BITS_1_..', 'signed token id for signing #2': 'S_T_ID_4_S_BITS_2_..', 'signed token id for signing #3': 'S_T_ID_4_S_BITS_3_..'}}


# sample 3DES secret key message (note: this is _NOT_ in canonical form -- I added extraneous carriage returns and indentation to aid readability.  Delete all carriage returns and whitespace indentation to get canonical form, as shown below):
#    (
#        (6:header
#            (
#                (8:protocol10:Mojo v0.94)
#                (12:message type3:key)))
#        (3:key
#            (
#                (10:key header
#                    (
#                        (4:type13:shared secret)
#                        (12:cryptosystem43:Triple DES, Encrypt-Decrypt-Encrypt, 3 Keys)
#                        (5:usage28:only for encrypting sessions)))
#                (10:key values
#                    (
#                        (17:shared secret key192:SHARED_SECRET_KEY_BITS..........................................................................................................................................................................))))))

# sample 3DES secret key message in canonical form
_sample_3DES_secret_key_message='(4:dict(6:string6:header)(4:dict(6:string12:message type)(6:string3:key)(6:string8:protocol)(6:string10:Mojo v0.94))(6:string3:key)(4:dict(6:string10:key header)(4:dict(6:string12:cryptosystem)(6:string43:Triple DES, Encrypt-Decrypt-Encrypt, 3 Keys)(6:string4:type)(6:string13:shared secret)(6:string5:usage)(6:string28:only for encrypting sessions))(6:string10:key values)(4:dict(6:string17:shared secret key)(6:string192:SHARED_SECRET_KEY_BITS..........................................................................................................................................................................))))'

mojo_test_flag = 0



def run():
    import RunTests
    RunTests.runTests(["MojoKey"])
    pass


#### this runs if you import this module by itself
if __name__ == '__main__':
    run()

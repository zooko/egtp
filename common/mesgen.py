#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

# standard modules
import modval
import xdrlib
from xdrlib import Packer,Unpacker
import tripledescbc
from sha import sha
import traceback
from bsddb3 import db, dbobj
from cPickle import dumps, loads
import threading
import traceback
import os
import time
import types

# pyutil modules
from debugprint import debugprint

# (old-)EGTP modules
import Cache
from CleanLogDb import CleanLogDbEnv
import HashRandom
import MojoKey
import confutils
import cryptutil
import fileutil
from humanreadable import hr
import idlib
import mencode
import mojosixbit
import mojoutil
import randsource

true = 1
false = 0

SIZE_OF_MODULAR_VALUES = 128
SIZE_OF_UNIQS = 20
HARDCODED_RSA_PUBLIC_EXPONENT = 3


# Size of public keys generated here-in.
SIZE_OF_PUBLIC_KEYS = SIZE_OF_MODULAR_VALUES

MINS_BETWEEN_DB_CHECKPOINTS = 5

#### !!!! XXXX TODO: add check that counterparty is not using weak public key size.  --Zooko 2000-07-16
# Size of symmetric keys.
SIZE_OF_SYMMETRIC_KEYS = 24

class Error(StandardError): pass

class NoCounterpartyInfo(Error): pass

class UnknownSession(Error):
    """
    raised by mesgen.parse() when the incoming message referenced an unknown session id;
    CommsHandlers may want to catch this and if possible using the given transport mechanism
    send back an indication that they didn't recognize the session id.
    Always contains an invalidate_session_msg member which contains a short message that,
    if possible to send back to the sender, will tell it to invalidate this session id.
    """
    # CryptoCommsHandler catches and uses this
    args = 'unknown session id'
    def __init__(self, id_in, counterparty_id):
        assert len(id_in) == SIZE_OF_UNIQS
        assert len(counterparty_id) == SIZE_OF_UNIQS
        self.invalidate_session_msg = '\000\000\002\002' + id_in + counterparty_id

# raised by mesgen.parse() when an 'invalidate session' message is received and handled successfully
class SessionInvalidated(Error): pass


def _mix_counterparties(cp1, cp2, data):
    assert type(cp1) == type('')
    assert type(cp2) == type('')
    assert type(data) == type('')
    p = Packer()
    p.pack_string(cp1)
    p.pack_string(cp2)
    p.pack_string(data)
    return sha(p.get_buffer()).digest()

class SessionKeeper:
    class ExtRes:
        """
        This is for holding things (external resources) that SK needs to finalize after SK is killed.  (post-mortem finalization)
        """
        def __init__(self, db_env, session_map, counterparty_map):
            self.db_env = db_env
            self.session_map = session_map
            self.counterparty_map = counterparty_map

        def __del__(self):
            debugprint("%s.__del__()\n", args=(self,))
            if self.session_map is not None :
                self.session_map.close()
                self.session_map = None
            if self.counterparty_map is not None :
                self.counterparty_map.close()
                self.counterparty_map = None
            if self.db_env is not None :
                self.db_env.nosyncerror_txn_checkpoint(0)
                self.db_env.close()
                self.db_env = None

    def __init__(self, dbparentdir=None, dir=None, serialized = None, maxitems = 1000, recoverdb=true):
        """
        You can pass either dir or dbparentdir, but not both.  You pass `dbparentdir' if you
        don't know the id of the key (either because the key is being created or because it is
        being de-serialized).  In that case, SessionKeeper creates a new sub-directory of
        dbparentdir which is named by the mojosixbit encoding of the id of the key.  For
        example, you pass dbparentdir == "...mtmdb/", and it creates
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/" and puts the key in a subdirectory named
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/mesgen/".


        You pass `dir' if you already know the directory that the key is stored in.  For
        example, you pass dir == "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/" and it looks in
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/mesgen/" and uses the key therein.


        @param dbparentdir the directory for all keys;  Subdirectories will be located or
            created, named by the mojosixbit encoding of the hash of the key.
        @param dir the directory for this particular key

        @precondition Exactly one of (dbparentdir, dir) must be not None.: ((dbparentdir is not None) and (dir is None)) or ((dbparentdir is None) and (dir is not None)): "dbparentdir: %s, dir: %s" % (hr(dbparentdir), hr(dir))
        """
        assert ((dbparentdir is not None) and (dir is None)) or ((dbparentdir is None) and (dir is not None)), "precondition: Exactly one of (dbparentdir, dir) must be not None." + " -- " + "dbparentdir: %s, dir: %s" % (hr(dbparentdir), hr(dir))

        if serialized:
            debugprint("COMPLAINT: passing in serialized secret keys is the old-style, just-a-hack-for-debug way of doing things.  You really want to just give me the directory to start from and I'll get the secret key stored in there in a file.\n", v=3)

        if dir:
            # The dbdir is under dir and named "mesgen".
            self._dir = os.path.normpath(dir)
            self._dbdir = os.path.normpath(os.path.join(self._dir, "mesgen"))

            if not serialized:
                f = open(os.path.normpath(os.path.join(dir, "key")), "r")
                serialized = f.read()
                f.close()

            skdict = mencode.mdecode(serialized)
            keyMV = modval.new_serialized(mojosixbit.a2b(skdict['private key serialized']))
  
            self.__my_public_key = MojoKey.makePublicRSAKeyForCommunicating(keyMV)
            self.__my_public_key_id = idlib.make_id(self.__my_public_key, '')
        else:
            # The dbdir is under dbparentdir, under my id, and is named "mesgen".

            if serialized:
                skdict = mencode.mdecode(serialized)
                keyMV = modval.new_serialized(mojosixbit.a2b(skdict['private key serialized']))
            else:
                keyMV = modval.new_random(SIZE_OF_PUBLIC_KEYS, HARDCODED_RSA_PUBLIC_EXPONENT)

            self.__my_public_key = MojoKey.makePublicRSAKeyForCommunicating(keyMV)
            self.__my_public_key_id = idlib.make_id(self.__my_public_key, 'broker')

            myid_aa = idlib.to_mojosixbit(self.__my_public_key_id)

            self._dir = os.path.normpath(os.path.join(dbparentdir, myid_aa))
            self._dbdir = os.path.normpath(os.path.join(self._dir, "mesgen"))
            fileutil.make_dirs(self._dbdir)

        # this lock is used to force single threaded access to this object as we've been having occasional DB_LOCK_DEADLOCK
        # problems with the database, most likely due to TCPCommsHandler accessing it from the asyncore thread as well as
        # CryptoCommsHandler accessing it from the DoQ thread.
        self.lock = threading.Lock()

        db_env = CleanLogDbEnv()
        db_env.set_lk_detect(db.DB_LOCK_DEFAULT)
        if recoverdb:
            recoverflag = db.DB_RECOVER
        else:
            recoverflag = 0

        privateflag = db.DB_PRIVATE

        try:
            db_env.open(self._dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | privateflag | recoverflag)
        except db.DBError, dbe:
            debugprint('Failed to open the database environment the first time, reason: %s\nTrying again...\n', args=(dbe,), vs='mesgen', v=2)
            try:
                db_env.open(self._dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | privateflag | recoverflag | db.DB_RECOVER)
            except db.DBError, dbe:
                debugprint('Failed to open the database environment the second time, reason: %s\nTrying again...\n', args=(dbe,), vs='mesgen', v=2)
                # XXX DOUBLE CHOCOLATEY HACK sometimes trying *again* after one open *without* DB_RECOVER works.
                db_env.open(self._dbdir, db.DB_CREATE | db.DB_INIT_MPOOL | db.DB_INIT_LOCK | db.DB_THREAD | db.DB_INIT_LOG | db.DB_INIT_TXN | privateflag | recoverflag & (~db.DB_RECOVER))

        self.__key = keyMV
        # maps id_in to counterparty id
        session_map = dbobj.DB(db_env)
        session_map.open('session_map', db.DB_BTREE, db.DB_CREATE | db.DB_THREAD )
        # maps counterparty id to [session_id_in, session_id_out, symmetric_key, header, full pk]
        # (XXX session_id_in in counterparty_map is never used, that's what session_map is for)
        counterparty_map = dbobj.DB(db_env)
        counterparty_map.open('counterparty_map', db.DB_BTREE, db.DB_CREATE | db.DB_THREAD )
        self.extres = SessionKeeper.ExtRes(db_env, session_map, counterparty_map)
        # maps header ids to content of headers for memoization
        self.__cached_headers = Cache.CacheSingleThreaded(maxitems)

        self.store_key(self.__my_public_key)

        keyfile = os.path.normpath(os.path.join(self._dir, "key"))
        f = open(keyfile, "w")
        f.write(self.serialize())
        f.close()

    def serialize(self):
        d = {'private key serialized': mojosixbit.b2a(self.__key.get_private_key_encoding())}
        return mencode.mencode(d)

    def get_private_key_encoding(self):
        return self.__key.get_private_key_encoding()

    def get_public_key(self):
        return self.__my_public_key

    def get_public_key_id(self):
        """
        @deprecated in favor of `get_id()'
        """
        return self.get_id()

    def get_id(self):
        return self.__my_public_key_id

    def got_ack(self, counterparty_id):
        self.lock.acquire()
        try:
            return self.__got_ack(counterparty_id)
        finally:
            self.lock.release()

    def __got_ack(self, counterparty_id):
        """
        Called when a message comes in for a not set up connection.

        @precondition `counterparty_id' must be  an id.: idlib.is_sloppy_id(counterparty_id): "id: %s" % hr(id)
        """
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be  an id." + " -- " + "id: %s" % hr(id)

        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')

        self.extres.db_env.nosyncerror_txn_checkpoint(MINS_BETWEEN_DB_CHECKPOINTS)
        trans = self.extres.db_env.txn_begin()
        try:
            # maps counterparty id to [session_id_in, session_id_out, symmetric_key, header, full pk]
            session_id_in, session_id_out, symmetric_key, _header, full_key = loads(self.extres.counterparty_map.get(counterparty_id, txn=trans, flags=db.DB_RMW))[:5]

            # remove the header (to signify our acknowledgement of their session acceptance)
            assert len(symmetric_key) == SIZE_OF_SYMMETRIC_KEYS
            assert MojoKey.publicRSAKeyIsSane(full_key)
            assert MojoKey.publicKeyForCommunicationSecurityIsWellFormed(full_key)
            self.extres.counterparty_map.put(counterparty_id, dumps([session_id_in, session_id_out, symmetric_key, None, full_key], 1), txn=trans)
            trans.commit()
            trans = None
        finally:
            if trans is not None:
                trans.abort()
        
    def parse_header(self, header):
        self.lock.acquire()
        try:
            return self.__parse_header(header)
        finally:
            self.lock.release()

    def __parse_header(self, header):
        """
        Parses a header and stores information contained in it as necessary
        
        Returns (counterparty pub key sexp, symmetric key) throws Error
        """
        assert type(header) == type('')
        try:
            hash = sha(header).digest()
            cached = self.__cached_headers.get(hash)
            if cached is not None:
                return cached
            u = Unpacker(header)
            # messages start with the hash of the recipient's public id
            recipient_id = u.unpack_fstring(SIZE_OF_UNIQS)
            if recipient_id != self.__my_public_key_id:
                raise Error, 'message not intended for me'
            # unpack PK encrypted public key
            encrypted_key = u.unpack_string()
            self.__key.set_value_string(encrypted_key)
            self.__key.decrypt()   # PKop
            decrypted = self.__key.get_value()

            try:
                symmetric_key = cryptutil.oaep_decode(decrypted[1:]) # Leave off the initial 0 byte. ### XX check whether it really is 0 and raise bad-encoding error if not.  --Zooko 2000-07-29
            except cryptutil.OAEPError, le:
                raise Error, 'bad encryption -- pad badding: padded: %s, Error: %s' % (`decrypted`, `le.args`)

            iv = u.unpack_fstring(8)
            # first half of the MAC # XXX A.K.A. the key?  --Zooko 2000-07-29
            prefix = header[:u.get_position()]
            # all data except the symmetric key and recipient, encrypted
            encrypted = u.unpack_string()
            u.done()

            decrypted = tripledescbc.new(symmetric_key).decrypt(iv, encrypted)                
            u = Unpacker(decrypted)
            # the full public key of the sender
            sender_key = u.unpack_string()
            full_key = MojoKey.makePublicRSAKeyForCommunicating(modval.new(sender_key, HARDCODED_RSA_PUBLIC_EXPONENT))
            full_key_id = idlib.make_id(full_key, 'broker')
            # the session id for messages sent 'here'
            id_in = _mix_counterparties(full_key_id, self.__my_public_key_id, u.unpack_fstring(SIZE_OF_UNIQS))
            # the session id for messages sent 'there'
            id_out = _mix_counterparties(full_key_id, self.__my_public_key_id, u.unpack_fstring(SIZE_OF_UNIQS))
            # check that the pk encrypted symmetric key used to send this message is the same was generated properly
            strl = u.unpack_fstring(SIZE_OF_UNIQS)
            sr = HashRandom.SHARandom(_mix_counterparties(full_key_id, self.__my_public_key_id, strl))
            spaml = sr.get(SIZE_OF_SYMMETRIC_KEYS)
            if symmetric_key != spaml:
                raise Error, 'improperly generated key'
            # the second half of what's in the MAC # XXX A.K.A. the message?  --Zooko 2000-07-29
            end = decrypted[:u.get_position()]
            # the signature of everything
            signature = u.unpack_fstring(len(sender_key))
            u.done()
            
            # debugprint("------ ------ ------ ------ hmachish(key=%s, message=%s)\n" % (`symmetric_key`, `end`))
            summary = cryptutil.hmacish(key=symmetric_key, message=end)
            
            x = modval.new(sender_key, HARDCODED_RSA_PUBLIC_EXPONENT, signature)
            x.undo_signature()   # PKop
            signed_value = x.get_value()

            try:
                thingie = cryptutil.oaep_decode(signed_value[1:]) # Leave off the initial 0 byte. ### XX check whether it really is 0 and raise bad-encoding error if not.  --Zooko 2000-07-29
            except cryptutil.OAEPError, le:
                raise Error, 'bad encryption -- pad badding: padded: %s, Error: %s' % (`signed_value`, `le.args`)
                
            if thingie != summary:
                raise Error, 'bad signature: %s != %s' % (`thingie`, `summary`)

            self.extres.db_env.nosyncerror_txn_checkpoint(MINS_BETWEEN_DB_CHECKPOINTS)
            trans = self.extres.db_env.txn_begin()
            try:
                # store session info if it's a new one
                if self.extres.counterparty_map.get(full_key_id, txn=trans, flags=db.DB_RMW) is None :
                    if self.extres.session_map.get(id_in, txn=trans, flags=db.DB_RMW) is not None :
                        raise Error, 'a session with the specified incoming id already exists'
                    assert len(symmetric_key) == SIZE_OF_SYMMETRIC_KEYS
                    self.extres.session_map.put(id_in, full_key, txn=trans)
                    self.extres.counterparty_map.put(full_key_id, dumps([id_in, id_out, symmetric_key, None, full_key], 1), txn=trans)
                else:
                    # Hmm.. We already had a session for this counterparty.
                    # this means that most likely we both tried to send each other messages to establish a session
                    # at the same time or at different times but one message got lost; usually due to the other
                    # counterparty being offline at the time or having just switched relay servers.
                    #
                    # TODO implement this:
                    #   Accept and store this key and use it in the future.  Keep the current key available
                    #   as well incase they get the session establishing message we sent them and switch to
                    #   using the session that we setup ourselves.
                    # What this would do:
                    #   prevent the current situation of always sending the header to/from counterparties
                    #   where initiating session establishing messages have crossed.  This is good because
                    #   full header messages are a bit larger and require two PKops on the receiver if the
                    #   header is not currently in its in memory parsed headers cache.
                    pass
                result = (full_key, symmetric_key)
                self.__cached_headers[hash] = result
                trans.commit()
                trans = None
                return result
            finally:
                if trans is not None:
                    trans.abort()
        except (modval.Error, tripledescbc.Error, xdrlib.Error, EOFError), le:
            debugprint("got error in mesgen.__parse_header(): %s", args=(le,), v=4, vs="debug")
            raise Error, le

    def store_key(self, full_key):
        """
        @idempotent
        """
        if self.extres.counterparty_map.has_key(idlib.make_id(full_key, 'key')):
            return

        self.lock.acquire()
        try:
            return self.__store_key(full_key)
        finally:
            self.lock.release()

    def __store_key(self, full_key):
        self.extres.db_env.nosyncerror_txn_checkpoint(MINS_BETWEEN_DB_CHECKPOINTS)
        trans = self.extres.db_env.txn_begin()
        try:
            key_id = sha(full_key).digest()
            if self.extres.counterparty_map.get(key_id, txn=trans, flags=db.DB_RMW) is not None :
                return
            id_in_rep = randsource.get(SIZE_OF_UNIQS)
            id_in = _mix_counterparties(self.__my_public_key_id, key_id, id_in_rep)
            id_out_rep = randsource.get(SIZE_OF_UNIQS)
            id_out = _mix_counterparties(self.__my_public_key_id, key_id, id_out_rep)
            key_seed = randsource.get(SIZE_OF_UNIQS)
            sr = HashRandom.SHARandom(_mix_counterparties(self.__my_public_key_id, key_id, key_seed))
            symmetric_key = sr.get(SIZE_OF_SYMMETRIC_KEYS)
            iv = randsource.get(8)

            p = Packer()
            p.pack_fstring(SIZE_OF_UNIQS, key_id)
            x = MojoKey.makeRSAPublicKeyMVFromSexpString(full_key)

            padded = '\000' + cryptutil.oaep(symmetric_key, len(self.__key.get_modulus()) - 1) # The prepended 0 byte is to make modval happy.
            assert len(padded) == len(self.__key.get_modulus())

            x.set_value_string(padded)
            x.encrypt()
            p.pack_string(x.get_value())
            p.pack_fstring(8, iv)

            penc = Packer()
            penc.pack_string(self.__key.get_modulus())
            penc.pack_fstring(SIZE_OF_UNIQS, id_out_rep)
            penc.pack_fstring(SIZE_OF_UNIQS, id_in_rep)
            penc.pack_fstring(SIZE_OF_UNIQS, key_seed)

            # debugprint("------ ------ ------ ------ hmachish(key=%s, message=%s)\n" % (`symmetric_key`, `penc.get_buffer()`))
            hashie = cryptutil.hmacish(key=symmetric_key, message=penc.get_buffer())

            paddedhashie = '\000' + cryptutil.oaep(hashie, len(self.__key.get_modulus()) - 1) # The prepended 0 byte is to make modval happy.
            assert len(paddedhashie) == len(self.__key.get_modulus())

            self.__key.set_value_string(paddedhashie)
            self.__key.sign()
            signature = self.__key.get_value()
            penc.pack_fstring(len(signature), signature)
            encrypted = tripledescbc.new(symmetric_key).encrypt(iv, penc.get_buffer())
            p.pack_string(encrypted)
            header = p.get_buffer()

            self.extres.counterparty_map.put(key_id, dumps([id_in, id_out, symmetric_key, header, full_key], 1), txn=trans)

            self.extres.session_map.put(id_in, full_key, txn=trans)
            trans.commit()
            trans = None
        finally:
            if trans is not None:
                trans.abort()

    def get_connect_info(self, counterparty_id):
        self.lock.acquire()
        try:
            return self.__get_connect_info(counterparty_id)
        finally:
            self.lock.release()

    def __get_connect_info(self, counterparty_id):
        """
        Returns either: {'header': ..., 'symmetric_key': ...} {'session_id_out': ..., 'symmetric_key': ...}
        
        Generates new connection info if there is none

        @precondition `counterparty_id' must be of the right form for an id.: idlib.is_sloppy_id(counterparty_id): "counterparty_id: %s" % hr(counterparty_id)
        """
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be of the right form for an id." + " -- " + "counterparty_id: %s" % hr(counterparty_id)

        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')

        self.extres.db_env.nosyncerror_txn_checkpoint(MINS_BETWEEN_DB_CHECKPOINTS)
        infopickle = self.extres.counterparty_map.get(counterparty_id)
        if infopickle is None:
            raise NoCounterpartyInfo, 'no counterparty information stored'

        # if the session has been verifiably set up, send the session id
        # otherwise send the full header
        session_id_out, symmetric_key, header = loads(infopickle)[1:4]
        if header is None :
            return {'session_id_out': session_id_out, 'symmetric_key': symmetric_key}
        else:
            return {'header': header, 'symmetric_key': symmetric_key}

    def get_session_info(self, id_in):
        self.lock.acquire()
        try:
            return self.__get_session_info(id_in)
        finally:
            self.lock.release()

    def __get_session_info(self, id_in):
        """
        Returns (counterparty_pub_key_sexp, symmetric_key, want ack) throws Error
        """
        self.extres.db_env.nosyncerror_txn_checkpoint(MINS_BETWEEN_DB_CHECKPOINTS)
        trans = self.extres.db_env.txn_begin()
        try:
            counterparty_pub_key_sexp = self.extres.session_map.get(id_in, txn=trans)
            if counterparty_pub_key_sexp is None:
                raise UnknownSession(id_in, self.get_id())
            counterparty_id = idlib.make_id(counterparty_pub_key_sexp, 'broker')
            try:
                symmetric_key, header = loads(self.extres.counterparty_map.get(counterparty_id, txn=trans))[2:4]
            except TypeError:
                # well, we did know about the session, but our counterparty database somehow didn't have an entry
                raise UnknownSession(id_in, self.get_id())
            return (counterparty_pub_key_sexp, symmetric_key, header is not None)
        finally:
            if trans is not None:
                trans.abort()

    def invalidate_session(self, bad_session_id_out, counterparty_id):
        self.lock.acquire()
        try:
            return self.__invalidate_session(bad_session_id_out, counterparty_id)
        finally:
            self.lock.release()

    def __invalidate_session(self, bad_session_id_out, counterparty_id):
        """
        Removes an outgoing session id from our database if counterparty_id matches the public key id
        associated with this session id.  Raises Error if bad_session_id_out is not associated with counterparty_id.
        """
        # maps counterparty id to [session_id_in, session_id_out, symmetric_key, header, full pk]
        try:
            stored_session_id_out = loads(self.extres.counterparty_map.get(counterparty_id, (None,None,None,None)))[1]
        except:
            stored_session_id_out = None
        debugprint("__invalidate_session for unverified cid %s, bad_session_id_out %s, stored_session_id_out %s\n", args=(counterparty_id, bad_session_id_out, stored_session_id_out), v=4, vs='mesgen')
        if idlib.equal(stored_session_id_out, bad_session_id_out):
            self.extres.counterparty_map.delete(counterparty_id)
        else:
            raise Error, "someone asked us to invalidate session_id_out %s, but they claimed that that session was with counterparty %s, but we do not have a that session id as our session id for that counterparty.  Not invalidating; we probably connected to broker that is now using a different key from the one we know for the CommStrat" % (`bad_session_id_out`, idlib.to_ascii(counterparty_id))
            # TODO this should be its own class of error, if caught it is -reasonable- (though not absolute in
            # in the rare case of someone malicious hijacking/inserting data into the TCP stream) to assume
            # that any of the messages you just sent down this TCP connection were undecryptable and should
            # be fast failed at this point.   [even in the malicious case above, its just becomes a convoluted
            # "denial of service" from you to the given counterparty that there are -much- easier ways to
            # accomplish without sniffing and hijacking connections]   -greg 2001-06-04


def create_MessageMaker(dbparentdir, recoverdb=true):
    return MessageMaker(dbparentdir=dbparentdir, dir=None, recoverdb=recoverdb)


def load_MessageMaker(dir, recoverdb=true):
    return MessageMaker(dbparentdir=None, dir=dir, recoverdb=recoverdb)


class MessageMaker:

    def __init__(self, dbparentdir=None, dir=None, serialized=None, recoverdb=true):
        """
        You can pass either dir or dbparentdir, but not both.  You pass `dbparentdir' if you
        don't know the id of the key (either because the key is being created or because it is
        being de-serialized).  In that case, SessionKeeper creates a new sub-directory of
        dbparentdir which is named by the mojosixbit encoding of the id of the key.  For
        example, you pass dbparentdir == "...mtmdb/", and it creates
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/" and puts the key in a subdirectory named
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/mesgen/".


        You pass `dir' if you already know the directory that the key is stored in.  For
        example, you pass dir == "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/" and it looks in
        "...mtmdb/ABCDEFGHIJKLMNOPQRSTUVWXYZA/mesgen/" and uses the key therein.


        @param dbparentdir the directory for all keys;  Subdirectories will be located or
            created, named by the mojosixbit encoding of the hash of the key.
        @param dir the directory for this particular key

        @precondition Exactly one of (dbparentdir, dir) must be not None.: ((dbparentdir is not None) and (dir is None)) or ((dbparentdir is None) and (dir is not None)): "dbparentdir: %s, dir: %s" % (hr(dbparentdir), hr(dir))
        """
        assert ((dbparentdir is not None) and (dir is None)) or ((dbparentdir is None) and (dir is not None)), "precondition: Exactly one of (dbparentdir, dir) must be not None." + " -- " + "dbparentdir: %s, dir: %s" % (hr(dbparentdir), hr(dir))

        if dir:
            self._session_keeper = SessionKeeper(dbparentdir=None, dir=dir, recoverdb=recoverdb)
        else:
            if serialized:
                mmdict = mencode.mdecode(serialized)
                skserialized = mmdict['session keeper']
                self._session_keeper = SessionKeeper(dbparentdir=dbparentdir, dir=None, serialized=skserialized, recoverdb=recoverdb)
            else:
                self._session_keeper = SessionKeeper(dbparentdir=dbparentdir, dir=None, recoverdb=recoverdb)

    def get_public_key(self):
        return self._session_keeper.get_public_key()

    def get_public_key_id(self):
        """
        @deprecated in favor of `get_id()'
        """
        return self.get_id()

    def get_id(self):
        return self._session_keeper.get_id()

    def get_counterparty_public_key(self, counterparty_id):
        """
        @precondition `counterparty_id' must be  an id.: idlib.is_sloppy_id(counterparty_id): "id: %s" % hr(id)
        """
        assert idlib.is_sloppy_id(counterparty_id), "precondition: `counterparty_id' must be  an id." + " -- " + "id: %s" % hr(id)

        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')

        return self._session_keeper.get_connect_info(counterparty_id)['symmetric_key']

    def store_key(self, pub_key_sexp):
        """
        @precondition `pub_key_sexp' must be a well-formed MojoKey.: MojoKey.publicKeyForCommunicationSecurityIsWellFormed(pub_key_sexp): "pub_key_sexp: %s" % hr(pub_key_sexp)

        @idempotent
        """
        assert MojoKey.publicKeyForCommunicationSecurityIsWellFormed(pub_key_sexp), "`pub_key_sexp' must be a well-formed MojoKey." + " -- " + "pub_key_sexp: %s" % hr(pub_key_sexp)

        self._session_keeper.store_key(pub_key_sexp)

    def generate_message(self, recipient_id, message):
        connect_info = self._session_keeper.get_connect_info(recipient_id)
        symmetric_key = connect_info['symmetric_key']
        p = Packer()
        if connect_info.has_key('session_id_out'):
            p.pack_fstring(4, '\000\000\000\001')
            p.pack_fstring(SIZE_OF_UNIQS, connect_info['session_id_out'])
        else:
            #debugprint('including full header on message to %s\n', args=(recipient_id,), vs='mesgen') # XXX verbose
            p.pack_fstring(4, '\000\000\000\000')
            p.pack_string(connect_info['header'])

        iv = randsource.get(8)
        p.pack_fstring(8, iv)
        pdec = Packer()
        pdec.pack_string(message)

        # debugprint("------ ------ ------ ------ hmachish(key=%s, message=%s)\n" % (`symmetric_key`, `message`))
        mac = cryptutil.hmacish(key=symmetric_key, message=message)

        pdec.pack_fstring(SIZE_OF_UNIQS, mac)
        encrypted = tripledescbc.new(symmetric_key).encrypt(iv, pdec.get_buffer())
        p.pack_string(encrypted)
        return p.get_buffer()

    # throws Error
    def parse(self, wired_string):
        """
        @returns (counterparty_pub_key_sexp, cleartext,)

        @raises SessionInvalidated if the incoming message was an "invalidate session" message \000\000\000\002.
        @raises UnknownSession error if the incoming message did not identify a known session key.

        @precondition `wired_string' must be a string.: type(wired_string) == types.StringType: "wired_string: %s :: %s" % (hr(wired_string), hr(type(wired_string)))
        @postcondition `counterparty_pub_key_sexp' is a public key.: MojoKey.publicRSAKeyForCommunicationSecurityIsWellFormed(counterparty_pub_key_sexp): "counterparty_pub_key_sexp: %s" % hr(counterparty_pub_key_sexp)
        """
        assert type(wired_string) == types.StringType, "precondition: `wired_string' must be a string." + " -- " + "wired_string: %s :: %s" % (hr(wired_string), hr(type(wired_string)))
        session = None

        try:
            u = Unpacker(wired_string)
            mtype = u.unpack_fstring(4)
            if mtype == '\000\000\000\000':   # a message with a full PK header
                header = u.unpack_string()
                iv = u.unpack_fstring(8)
                prefix = wired_string[:u.get_position()]
                encrypted = u.unpack_string()
                u.done()
                
                counterparty_pub_key_sexp, symmetric_key = self._session_keeper.parse_header(header)
                decrypted = tripledescbc.new(symmetric_key).decrypt(iv, encrypted)
                u = Unpacker(decrypted)
                message = u.unpack_string()
                mac = u.unpack_fstring(SIZE_OF_UNIQS)
                u.done()
                
                # debugprint("------ ------ ------ ------ hmachish(key=%s, message=%s)\n" % (`symmetric_key`, `message`))
                maccomp = cryptutil.hmacish(key=symmetric_key, message=message)

                if mac != maccomp:
                    raise Error, 'incorrect MAC'
                return (counterparty_pub_key_sexp, message)
            elif mtype == '\000\000\000\001':   # a message using an already established session id
                session = u.unpack_fstring(SIZE_OF_UNIQS)
                iv = u.unpack_fstring(8)
                prefix = wired_string[:u.get_position()]
                encrypted = u.unpack_string()
                u.done()
                
                counterparty_pub_key_sexp, symmetric_key, want_ack = self._session_keeper.get_session_info(session)
                decrypted = tripledescbc.new(symmetric_key).decrypt(iv, encrypted)

                u = Unpacker(decrypted)
                message = u.unpack_string()
                mac = u.unpack_fstring(SIZE_OF_UNIQS)
                u.done()

                counterparty_id = idlib.make_id(counterparty_pub_key_sexp, 'broker')

                # debugprint("------ ------ ------ ------ hmachish(key=%s, message=%s)\n" % (`symmetric_key`, `message`))
                maccomp = cryptutil.hmacish(key=symmetric_key, message=message)
                if mac != maccomp:
                    raise Error, 'incorrect MAC'
                if want_ack:
                    self._session_keeper.got_ack(counterparty_id)
                return (counterparty_pub_key_sexp, message)
            elif mtype == '\000\000\002\002':   # a short "message" invalidating an outgoing session id
                bad_session_id_out = u.unpack_fstring(SIZE_OF_UNIQS)
                unverified_counterparty_id = u.unpack_fstring(SIZE_OF_UNIQS)
                self._session_keeper.invalidate_session(bad_session_id_out, unverified_counterparty_id)
                raise SessionInvalidated, 'session_id %s with %s invalidated' % (`bad_session_id_out`, idlib.to_ascii(unverified_counterparty_id))
            else:
                raise Error, 'unsupported message type'
        except (modval.Error, tripledescbc.Error, xdrlib.Error, EOFError), le:
            debugprint("got error in mesgen.parse(): %s", args=(le,), v=4, vs="debug")
            if session is not None:
                raise UnknownSession(session, self.get_id())
            else:
                raise Error, le

def _help_test_create_MessageMaker():
    return create_MessageMaker("/var/tmp/RunTests")

def _help_test_load_MessageMaker(id):
    myid_aa = idlib.to_mojosixbit(id)
    dir = os.path.normpath(os.path.join("/var/tmp/RunTests/", myid_aa))
    return load_MessageMaker(dir)

def test_normal_operation():
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    mesgen1.store_key(key2)
    m1 = mesgen1.generate_message(id2, 'spam1')
    m2 = mesgen1.generate_message(id2, 'spam2')
    counterparty_pub_key_sexp, message = mesgen2.parse(m2)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam2'
    counterparty_pub_key_sexp, message = mesgen2.parse(m1)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam1'
    m3 = mesgen2.generate_message(id1, 'spam3')
    counterparty_pub_key_sexp, message = mesgen1.parse(m3)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
    assert message == 'spam3'
    # check to see that header is not on later messages
    m1a = mesgen1.generate_message(id2, 'spam1')
    assert len(m1a) < len(m1)
    m2a = mesgen1.generate_message(id2, 'spam2')
    assert len(m2a) < len(m2)

def disabledwedontdomultithreadingmesgenfornow_test_send_two_messages_at_once():
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    
    prestart1 = threading.Event()
    start1 = threading.Event()
    flag1 = threading.Event()
    def store_key1(start = start1, mesgen1 = mesgen1, key2 = key2, flag = flag1, prestart1=prestart1):
        prestart1.set()
        start.wait()
        mesgen1.store_key(key2)
        flag.set()
    prestart2 = threading.Event()
    flag2 = threading.Event()
    def store_key2(start = start1, mesgen1 = mesgen1, key2 = key2, flag = flag2, prestart2=prestart2):
        prestart2.set()
        start.wait()
        mesgen1.store_key(key2)
        flag.set()
    threading.Thread(target = store_key1).start()
    threading.Thread(target = store_key2).start()
    prestart1.wait()
    prestart2.wait()
    start1.set()
    flag1.wait(2)
    assert flag1.isSet()
    flag2.wait(2)
    assert flag2.isSet()

    m1holder = []
    m2holder = []
    start2 = threading.Event()
    flag3 = threading.Event()
    flag4 = threading.Event()
    def make_message1(start = start2, m1holder = m1holder, mesgen1 = mesgen1, id2 = id2, flag = flag3):
        start.wait()
        m1holder.append(mesgen1.generate_message(id2, 'spam'))
        flag.set()
    def make_message2(start = start2, m2holder = m2holder, mesgen1 = mesgen1, id2 = id2, flag = flag4):
        start.wait()
        m2holder.append(mesgen1.generate_message(id2, 'spam'))
        flag.set()
    threading.Thread(target = make_message1).start()
    threading.Thread(target = make_message2).start()
    xxx(time.sleep(1))
    start2.set()
    flag3.wait(2)
    assert flag3.isSet()
    assert len(m1holder) == 1
    flag4.wait(2)
    assert flag4.isSet()
    assert len(m2holder) == 1

    start3 = threading.Event()
    flag5 = threading.Event()
    flag6 = threading.Event()
    parseflag = threading.Event()
    def parse1(mesgen2 = mesgen2, wiremessage = m1holder[0], id1 = id1, flag = flag5, 
            parseflag = parseflag, start = start3):
        start.wait()
        counterparty_id, message = mesgen2.parse(wiremessage)
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be  an id." + " -- " + "id: %s" % hr(id)
        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')
        if not idlib.equal(counterparty_id, id1) or (message != 'spam'):
            parseflag.set()
        flag.set()
    def parse2(mesgen2 = mesgen2, wiremessage = m2holder[0], id1 = id1, flag = flag6, 
            parseflag = parseflag, start = start3):
        start.wait()
        counterparty_id, message = mesgen2.parse(wiremessage)
        assert idlib.is_sloppy_id(counterparty_id), "`counterparty_id' must be  an id." + " -- " + "id: %s" % hr(id)
        counterparty_id = idlib.canonicalize(counterparty_id, 'broker')
        if not equal(counterparty_id, id1) or (message != 'spam'):
            parseflag.set()
        flag.set()
    threading.Thread(target = parse1).start()
    threading.Thread(target = parse2).start()
    xxx(time.sleep(1))
    start3.set()
    flag5.wait(2)
    assert flag5.isSet()
    assert not parseflag.isSet()
    flag6.wait(2)
    assert flag6.isSet()
    assert not parseflag.isSet()

    m3 = mesgen1
    mesgen1 = mesgen2
    mesgen2 = m3
    i3 = id1
    id1 = id2
    id2 = i3
    k3 = key1
    key1 = key2
    key2 = k3

    m1holder = []
    m2holder = []
    start2 = threading.Event()
    flag3 = threading.Event()
    flag4 = threading.Event()
    def make_message1(start = start2, m1holder = m1holder, mesgen1 = mesgen1, id2 = id2, flag = flag3):
        start.wait()
        m1holder.append(mesgen1.generate_message(id2, 'spam'))
        flag.set()
    def make_message2(start = start2, m2holder = m2holder, mesgen1 = mesgen1, id2 = id2, flag = flag4):
        start.wait()
        m2holder.append(mesgen1.generate_message(id2, 'spam'))
        flag.set()
    threading.Thread(target = make_message1).start()
    threading.Thread(target = make_message2).start()
    xxx(time.sleep(1))
    start2.set()
    flag3.wait(2)
    assert flag3.isSet()
    assert len(m1holder) == 1
    flag4.wait(2)
    assert flag4.isSet()
    assert len(m2holder) == 1

    start3 = threading.Event()
    flag5 = threading.Event()
    flag6 = threading.Event()
    parseflag = threading.Event()
    def parse1(mesgen2 = mesgen2, wiremessage = m1holder[0], id1 = id1, flag = flag5, 
            parseflag = parseflag, start = start3):
        start.wait()
        counterparty_id, message = mesgen2.parse(wiremessage)
        if counterparty_id != id1 or message != 'spam':
            parseflag.set()
        flag.set()
    def parse2(mesgen2 = mesgen2, wiremessage = m2holder[0], id1 = id1, flag = flag6, 
            parseflag = parseflag, start = start3):
        start.wait()
        counterparty_id, message = mesgen2.parse(wiremessage)
        if counterparty_id != id1 or message != 'spam':
            parseflag.set()
        flag.set()
    threading.Thread(target = parse1).start()
    threading.Thread(target = parse2).start()
    xxx(time. sleep(1))
    start3.set()
    flag5.wait(2)
    assert flag5.isSet()
    assert not parseflag.isSet()
    flag6.wait(2)
    assert flag6.isSet()
    assert not parseflag.isSet()

def test_normal_operation_with_reconstruction():
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    mesgen1.store_key(key2)
    m1 = mesgen1.generate_message(id2, 'spam1')
    m2 = mesgen1.generate_message(id2, 'spam2')
    counterparty_pub_key_sexp, message = mesgen2.parse(m2)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam2'
    counterparty_pub_key_sexp, message = mesgen2.parse(m1)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam1'
    m3 = mesgen2.generate_message(id1, 'spam3')
    counterparty_pub_key_sexp, message = mesgen1.parse(m3)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
    assert message == 'spam3'
    # check to see that header is not on later messages
    m1a = mesgen1.generate_message(id2, 'spam1')
    assert len(m1a) != len(m1)
    m2a = mesgen1.generate_message(id2, 'spam2')
    assert len(m2a) != len(m2)
    del mesgen1
    del mesgen2

    mesgen1 = _help_test_load_MessageMaker(id1)
    mesgen2 = _help_test_load_MessageMaker(id2)
    mesgen1.store_key(key2)
    m1 = mesgen1.generate_message(id2, 'spam1')
    m2 = mesgen1.generate_message(id2, 'spam2')
    counterparty_pub_key_sexp, message = mesgen2.parse(m2)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam2'
    counterparty_pub_key_sexp, message = mesgen2.parse(m1)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam1'
    m3 = mesgen2.generate_message(id1, 'spam3')
    counterparty_pub_key_sexp, message = mesgen1.parse(m3)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
    assert message == 'spam3'
    m1a = mesgen1.generate_message(id2, 'spam1')
    assert len(m1a) == len(m1)
    m2a = mesgen1.generate_message(id2, 'spam2')
    assert len(m2a) == len(m2)

def test_interlock():
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    mesgen1.store_key(key2)
    mesgen2.store_key(key1)
    m1 = mesgen1.generate_message(id2, 'spam1')
    m2 = mesgen2.generate_message(id1, 'spam2')
    counterparty_pub_key_sexp, message = mesgen2.parse(m1)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    assert message == 'spam1'
    counterparty_pub_key_sexp, message = mesgen1.parse(m2)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
    assert message == 'spam2'

def test_send_self():
    mesgen = _help_test_create_MessageMaker()
    x = mesgen.generate_message(mesgen.get_id(), 'spam')
    pub_key_sexp, message = mesgen.parse(x)
    assert idlib.equal(idlib.make_id(pub_key_sexp, 'broker'), mesgen.get_id())
    assert message == 'spam'

def test_invalidate_session():
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    mesgen1.store_key(key2)
    m1a = mesgen1.generate_message(id2, 'spam1a')
    # send a message m1 -> m2
    counterparty_pub_key_sexp, message = mesgen2.parse(m1a)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
    # send a message back m2 -> m1 (acts as an ACK that the session & header was received properly)
    m2a = mesgen2.generate_message(id1, 'spam2a')
    counterparty_pub_key_sexp, message = mesgen1.parse(m2a)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
    # force mesgen2 to forget the session established by m1
    for m2_session_id_in in mesgen2._session_keeper.extres.session_map.keys():
        print "mesgen deleting session id", `m2_session_id_in`
        mesgen2._session_keeper.extres.session_map.delete(m2_session_id_in)
    # send a message m1 -> m2, but m2 has forgotten the session that will be used
    m1b = mesgen1.generate_message(id2, 'spam1b')
    assert m1b[:4] == '\000\000\000\001', 'message should have used an established session'
    assert 'm1b'
    try:
        mesgen2.parse(m1b)
        assert 0, "UnknownSession should have been raised"
    except UnknownSession, uks:
        try:
            mesgen1.parse(uks.invalidate_session_msg)
            assert 0, "SessionInvalidated should have been raised"
        except SessionInvalidated:
            pass
    # this should succeed normally, generating a new session
    m1c = mesgen1.generate_message(id2, 'spam1c')
    assert m1c[:4] == '\000\000\000\000', "message should have tried to setup a new session"
    counterparty_pub_key_sexp, message = mesgen2.parse(m1a)
    assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)

def test_Error():
    mesgen = _help_test_create_MessageMaker()
    x = mesgen.generate_message(mesgen.get_id(), 'spam')
    try:
        mesgen.parse(x + 'uh')
    except Error:
        return
    assert 0

def test_serialize_and_reserialize():
    testdir = "/var/tmp/RunTests"
    sk = SessionKeeper(dbparentdir=testdir, dir=None)

    id = sk.get_id()
    key = sk.get_public_key()

    del sk

    dir = os.path.normpath(os.path.join(testdir, idlib.to_mojosixbit(id)))
    
    sk2 = SessionKeeper(dbparentdir=None, dir=dir)

    assert sk2.get_public_key() == key

def _test_mesgen_speed(iterations=200):
    # "200 loop iterations generating and parsing 3 messages each took 2.26 seconds" -greg 2001-05-31 [333Mhz Celeron]
    mesgen1 = _help_test_create_MessageMaker()
    mesgen2 = _help_test_create_MessageMaker()
    id1 = mesgen1.get_id()
    id2 = mesgen2.get_id()
    key1 = mesgen1.get_public_key()
    key2 = mesgen2.get_public_key()
    mesgen1.store_key(key2)

    start_time = time.time()
    for x in xrange(iterations):
        m1 = mesgen1.generate_message(id2, 'spam1')
        m2 = mesgen1.generate_message(id2, 'spam2')
        counterparty_pub_key_sexp, message = mesgen2.parse(m2)
        assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
        assert message == 'spam2'
        counterparty_pub_key_sexp, message = mesgen2.parse(m1)
        assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id1)
        assert message == 'spam1'
        m3 = mesgen2.generate_message(id1, 'spam3')
        counterparty_pub_key_sexp, message = mesgen1.parse(m3)
        assert idlib.equal(idlib.make_id(counterparty_pub_key_sexp, 'broker'), id2)
        assert message == 'spam3'
    stop_time = time.time()
    print "%d loop iterations generating and parsing 3 messages each took %3.2f seconds" % (iterations, stop_time-start_time)


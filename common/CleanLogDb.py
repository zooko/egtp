## Subclass of DB that cleans up it's log files periodically

# pyutil modules
from debugprint import debugprint

from bsddb3 import db, dbobj
import re
import os
import time

CLEANING_INTERVAL = 60 * 60  # once an hour

logfile_pat = re.compile('^log.[0-9]*$')

class CleanLogDbEnv(dbobj.DBEnv):
    """
    This Subclass of DBEnv cleans up old logfiles when checkpointing, up to once per day...
    """
    def __init__(self,*_args,**_kwargs):
        apply(dbobj.DBEnv.__init__, (self,) + _args, _kwargs)
        self._last_logfile_cleanup = 0

    def open(self, *_args, **_kwargs):
        self._db_home = _args[0]
        return apply(dbobj.DBEnv.open, (self,) + _args, _kwargs)

    def set_flags(self, *_args, **_kwargs):
        return apply(dbobj.DBEnv.set_flags, (self,) + _args, _kwargs)
        
    def txn_checkpoint(self, *_args, **_kwargs):
        # first get a list of the files, then checkpoint, then delete from the list
        are_cleaning = 0
        if((time.time() - self._last_logfile_cleanup) > CLEANING_INTERVAL):
            are_cleaning = 1
            dlist = os.listdir(self._db_home)

        val = apply(dbobj.DBEnv.txn_checkpoint, (self,) + _args, _kwargs)
        
        if are_cleaning:
            self.cleanupLogfiles(dlist)
        return val
    
    def nosyncerror_txn_checkpoint(self, *_args, **_kwargs):
        val = None
        
        try:
            val = apply(self.txn_checkpoint, _args, _kwargs)
        except RuntimeWarning, e:
            # try again, this is a non-fatal intermittent error
            try:
                val = apply(self.txn_checkpoint, _args, _kwargs)
            except db.DBError, e:
                debugprint("ignoring db.DBError %s during txn_checkpoint\n", args=(e,), v=3, vs="CleanLogDb")
        return val
    
    def cleanupLogfiles(self, fileList):
        """
        Removes old logfiles.  Given a list of files, deletes all but
        the highest numbered two logfiles (most recent).
        """
        self._last_logfile_cleanup = time.time()
        l = filter(lambda a: logfile_pat.match(a), fileList)
        l.sort()
        if len(l) > 2:
            to_delete = l[:-2]
            debugprint("Cleaning up %s database logs for database %s.\n" % (len(to_delete), self._db_home))
            for file in to_delete:
                try:
                    os.unlink(os.path.join(self._db_home, file))
                except:
                    # done to ignore unlink errors, we're only trying to
                    # remove the file but if for some reason it doesn't
                    # work it shouldn't be fatal.  (i saw a rare error on
                    # windows where it wasn't working)
                    continue
        

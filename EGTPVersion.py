#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
__cvsid = '$Id: EGTPVersion.py,v 1.5 2002/03/13 20:37:48 zooko Exp $'

# standard modules
import string

# pyutil modules
import VersionNumber

# major, minor, micro (== bugfix release), nano (== not-publically-visible patchlevel), flag (== not-publically-visible UNSTABLE or STABLE flag)
versiontup = (0, 0, 2, 4,)
versionflag = 'UNSTABLE'
versionobj = VersionNumber.VersionNumber(string.join(map(str, versiontup), '.') + '-' + versionflag)
versionstr_full = versionobj.full_string()
versionstr = versionobj.terse_string()

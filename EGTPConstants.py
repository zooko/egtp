#  Copyright (c) 2001 Autonomous Zone Industries
#  Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
# CVS:
__cvsid = '$Id: EGTPConstants.py,v 1.1 2002/07/17 02:02:47 zooko Exp $'


# length of RSA public moduli in 8-bit bytes (octets)

# Note that it is allowable for some of the high order bits to be 0.  It is even
# allowable for more than 8 of those bits to be 0 without changing the "length" of the
# modulus.  This is really then the log-base-2 of the size of the space from which we
# randomly choose such values, rather than the "length" of the binary encoding of
# any particular value.

SIZE_OF_MODULAR_VALUES = 1024/8


# Your code should probably be written to work with any public exponent.  It is best not to use
# this constant.  But it is here because mesgen uses it currently.
HARDCODED_RSA_PUBLIC_EXPONENT = 3


# size of ids, secrets, random numbers, salt and other things that must be universally unique
# in 8-bit bytes (octets)
# You absolutely cannot change this number.  In fact, it is just being hardcoded in all over the place
# and this variable is useful only as documentation.
SIZE_OF_UNIQS = 20



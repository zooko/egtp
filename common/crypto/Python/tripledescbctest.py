#
#  Copyright (c) 2000 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#
import tripledescbc

x = tripledescbc.new("hegonugetonugetorgcronig")
iv = "oeugoteg"
plaintext = "this is a plaintext message testing testing 1 2 3"
print "plaintext =",plaintext
ciphertext = x.encrypt(iv,plaintext)
print "ciphertext =",`ciphertext`
verify = x.decrypt(iv,ciphertext)
print "verification =",verify

print
plaintext = ""
print "plaintext (the null string) =",plaintext
ciphertext = x.encrypt(iv,plaintext)
print "ciphertext =",`ciphertext`
verify = x.decrypt(iv,ciphertext)
print "verification =",verify

import os
import sys
import string
import re
# distutils is included with python 1.6 and later, go grab a copy if you use python 1.5.2.
from distutils.core import setup, Extension
import getopt

include_dirs = []
library_dirs = []
libraries = []
define_macros = []
extra_compile_args = []
extra_link_args = []
extra_objects = []

def usage(le):
    # print "hello weirdling!"
    print "Hey -- this setup.py script accepts opts like this: getopt.getopt(sys.argv[1:], \"l:a:\", [\"libraries=\", \"extra_link_args=\"]); libraries and args are space-separated (but need to be passed in as one bash word, i.e. the entire space separated list of libraries e.g. --libraries=\"foo bar spam\")"
    print "got error: %s" % `le`

# See if there are some special library flags passed in as arguments.
shortopts="l:a:I:c:L:o:"
longopts=["libraries=", "extra_link_args=", "include_dirs=", "extra_compile_args=", "library_dirs=", "extra_objects=",]
try:
    opts, args = getopt.getopt(sys.argv[1:], shortopts, longopts)
except getopt.GetoptError, le:
    # print help information and exit:
    usage(le)
    sys.exit(2)

# print "opts: ", opts
# print "args: ", args

for o, a in opts:
    if o in ("-l", "--libraries",):
        libraries.extend(string.split(a))
    if o in ("-a", "--extra_link_args",):
        extra_link_args.extend(string.split(a))
    if o in ("-I", "--include_dirs",):
        include_dirs.extend(string.split(a))
    if o in ("-c", "--extra_compile_args",):
        extra_compile_args.extend(string.split(a))
    if o in ("-L", "--library_dirs",):
        library_dirs.extend(string.split(a))
    if o in ("-o", "--extra_objects",):
        extra_objects.extend(string.split(a))

# print "libraries: ", libraries
# print "extra_link_args:", extra_link_args

# Now consume the options so that setup's getopt won't barf on them.
# This is very ugly and I'm pretty sure distutils isn't meant to be used this way.
# After I get it working I'll ask distutils-sig.  --Zooko 2001-10-17
# # print "yodellleeeo: %s" % `sys.argv`
i = len(sys.argv)
for ni in range(1, len(sys.argv)):
    i = i - 1
    # print i
    # print sys.argv[i]
    for shortopt in shortopts:
        if shortopt != ':' and (len(sys.argv) > i) and (len(sys.argv[i]) >= 2) and (sys.argv[i][:2] == "-"+shortopt):
            # print "munch munch: %s" % `i`
            del sys.argv[i]
            # print "done munch munch: %s" % `i`
    for longopt in longopts:
        if (len(sys.argv) > i) and (len(sys.argv[i]) >= len(longopt) + 2) and (sys.argv[i][:len(longopt)+2] == "--" + longopt):
            # print "munch munch: %s" % `i`
            del sys.argv[i]
            # print "done munch munch: %s" % `i`

# print "eedleyoyo!: %s" % `sys.argv`
if os.environ.has_key('CRYPTOPP_DIR'):
    cryptoppdir = os.environ['CRYPTOPP_DIR']
    if not os.path.isdir(cryptoppdir) :
        raise SystemExit, "Your CRYPTOPP_DIR environment variable is incorrect.  is not dir: cryptoppdir: %s" % cryptoppdir
else:
    raise SystemExit, "Your CRYPTOPP_DIR environment variable must be set."

### the following code is to make it use `g++' instead of `gcc' to compile and link.
### It is a very ugly way to do it, but I can't figure out a nice way to do it.   --Zooko 2001-09-16
### I got this code from http://mail.python.org/pipermail/python-list/2001-March/032381.html
from distutils import sysconfig
save_init_posix = sysconfig._init_posix
def my_init_posix():
    print 'my_init_posix: changing gcc to g++'
    save_init_posix()
    g = sysconfig._config_vars
    g['CC'] = 'g++'
    g['LDSHARED'] = 'g++ -shared'
sysconfig._init_posix = my_init_posix

if sys.platform == 'win32' and '--compiler=mingw32' not in args:
    # vc++ complained to me and told me to add /GX so I did
    define_macros.extend((('PYTHON_MODULE', None), ('WIN32', None), ('GX', None),))
    # os.environ['CFLAGS'] = '/DPYTHON_MODULE /DWIN32 /GX'
    include_dirs.append(os.path.join(os.path.join(os.environ['EXTSRCWINDIR'], 'Python-1.6'), 'PC'))
    library_dirs.extend([os.path.join(sys.prefix, 'PCbuild'), os.path.join(cryptoppdir, 'Release')])
    libraries.append('cryptlib-mojo')
elif '--compiler=mingw32' in args:
    define_macros.extend([('PYTHON_MODULE', None),])
    extra_compile_args.extend(['-w',])
    # os.environ['CFLAGS'] = '-DPYTHON_MODULE -w'

    library_dirs.extend([cryptoppdir])
    libraries.insert(0, 'stdc++')
    libraries.insert(0, 'cryptopp')
else:
    define_macros.extend([('PYTHON_MODULE', None),])
    extra_compile_args.extend(['-w',])
    # os.environ['CFLAGS'] = '-DPYTHON_MODULE -w'

    library_dirs.extend([cryptoppdir])
    libraries.insert(0, 'cryptopp')

# The Makefile should have already decided which version of Crypto++ we use and set one of these env vars for us:
cryptoppversion = os.environ.get('CRYPTOPP_VERSION')
if cryptoppversion is None:
    print "WARNING: Makefile didn't set CRYPTOPP_VERSION env var.  Using 4.0 by default"
    cryptoppversion = "4.0"

if cryptoppversion == "3.2":
    define_macros.extend([('CRYPTOPP_32', None),])
elif cryptoppversion == "4.0":
    define_macros.extend([('CRYPTOPP_40', None),])
elif cryptoppversion == "4.1":
    define_macros.extend([('CRYPTOPP_41', None),])
elif cryptoppversion == "4.2":
    define_macros.extend([('CRYPTOPP_42', None),])

# On FreeBSD we -finally- found that -lgcc was the magic needed linker flag to
# prevent the "undefined symbol: __pure_virtual" problem when attempting to
# import the evilcryptopp.so module.
if re.search('bsd', sys.platform, re.I):
    libgcc_dir = os.path.dirname( os.popen("gcc -print-libgcc-file-name").readline()[:-1] )
    library_dirs.append(libgcc_dir)
    libraries.append('gcc')

if os.environ.has_key('CRYPTOPP_DIR'):
    cryptoppdir = os.environ['CRYPTOPP_DIR']
    if not os.path.isdir(cryptoppdir) :
        raise SystemExit, "Your CRYPTOPP_DIR environment variable is incorrect.  is not dir: cryptoppdir: %s" % cryptoppdir
else:
    raise SystemExit, "Your CRYPTOPP_DIR environment variable must be set."

include_dirs.extend(["../", cryptoppdir])

setup ( name = "evilcryptopp",
        version = "1.0.0",
        author = "Autonomous Zone Industries",
        author_email = "mojonation-devel@lists.sourceforge.net",
        url = "http://sourceforge.net/projects/mojonation/",
        ext_modules = [
            Extension(
                "evilcryptopp",
                ["modval.cpp", "../wrappedrsa.cpp", "../randsource_methods.cpp", "evilcryptopp.cpp", "tripledescbc.cpp", "randsource.cpp"],
                # The BERKELEYDB_DIR environment variable is required
                include_dirs=include_dirs,
                define_macros=define_macros,
                extra_compile_args=extra_compile_args,
                extra_link_args=extra_link_args,
                extra_objects=extra_objects,
                library_dirs=library_dirs,
                libraries=libraries,
            )
        ],
      )


#!/bin/sh

# here's how to cvs checkout and compile egtp on a Unix:

# DEPENDENCIES:
# First, acquire all the necessary packages.
# REQUIRED: C/C++ compiler, GNUmake, Python interpreter with threading and zlib 
# support, Python development headers, Python distutils, libjpeg 6.2 development
# headers, zlib development headers.
# RECOMMENDED: we use GCC 3.0.3, and gnumake 3.79.1.  We recommend python 2.2.
# KNOWN TO WORK: GCC v2.95.[34], and v3.0.[123] are known to work.  The 
# following Python versions are known to work: v1.5.2, v1.6, v2.0.[01], 
# v2.1.[01], v2.2.

# Users of debian can enter the following command line to get these packages:
# sudo apt-get install cvs python-dev python-zlib make g++ libjpeg62-dev zlib1g-dev
# Users of other Linuxes or Unixes can do your equivalent of that line.


# BUILDING AND RUNNING IT
# Then you can execute the rest of this script as a shell script, or read it and 
# cut and paste the commands into your shell.

# You need to read the rest of this file only if something fails, if you are 
# curious about different options, or if you are building a package on one 
# machine to run on a different machine.

mkdir egtp
cd egtp

touch ${HOME}/.cvspass
if [ "X`grep anonymous@cvs.egtp ${HOME}/.cvspass`" = "X" ]; then
   echo ":pserver:anonymous@cvs.egtp.sourceforge.net:/cvsroot/egtp A" >>${HOME}/.cvspass
fi

cvs -z3 -d:pserver:anonymous@cvs.egtp.sourceforge.net:/cvsroot/egtp co egtp extsrc

# If you have already checked out the egtp and extsrc modules, then instead of 
# "co"'ing egtp and extsrc here, you cd into each directory and run 
# "cvs update -Pd" in each one.

# Set these two environment variables to be the absolute path to the respective directories:
# Work around a Solaris bug
if [ "`uname -s`" = "SunOs" ]; then
  PWD=`pwd`
  echo "Warning: you will need GNU tar in your PATH to compile Mnet."
  echo "You may also need to put /usr/local/lib into LD_LIBRARY_PATH"
fi

EGTPDIR=${PWD}/egtp; export EGTPDIR
EXTSRCDIR=${PWD}/extsrc; export EXTSRCDIR
cd egtp

if which gmake >/dev/null 2>&1
then
  gmake MAKE=gmake all
elif gmake --version 2>&1 | grep ^GNU >/dev/null
then
  gmake MAKE=gmake all
else
  echo "Warning: you may need gmake to compile egtp!"
  make all
fi
# This 'make all' step takes a while if this is the first time you've compiled.

# Now see if it passes all unit tests:
./unittest.sh


### EXTRA OPTIONS AND DETAILS

# By the way, you can also try "branch stable".  To update a directory to reflect
# the contents of the stable branch, cd into the directory and run
# cvs update -Pd -r branch_stable
# To update a directory to reflect the contents of the current unstable branch,
# cd into it and run
# cvs update -Pd -A

# Also by the way, you almost never have to `make clean' with egtp, and
# making clean and then rebuilding all can take a long time.  Therefore 
# I suggest that you never make clean unless (a) you see that the extsrc 
# directory has been updated (this happens rarely), or (b) when you start the 
# broker it immediately exits with an error message about libraries or modules 
# or importing or (c) you see in the following list that you are upgrading to a 
# version that requires a rebuild:

# List started 2001-09-21
# I don't remember the last version that needed a make clean.
# 2001-10-12, Mojo Nation v0.997.3: nope, you still don't need to make clean.
# 2001-11-28, Mojo Nation v0.998 or 0.999: okay, due to PyXML changes, you might 
#    need to make clean when upgrading past this version number
# 2002-02-12, Mnet v0.5.0: nope, you don't need to make clean.
# 2002-03-11, egtp v0.0.2.1-UNSTABLE: nope, you don't need to make clean.


# BUILDING PACKAGES TO DISTRIBUTE TO OTHERS:
# If you are building a package for yourself to use, you can use any version of 
# Python.  However, if you want to run the package on a different machine than 
# it was built, be aware that egtp packages built with a version of Python < 2.1 
# cannot run with a version of Python >= 2.1, nor can egtp built with a 
# version >= 2.2 be run with a version of Python < 2.2.
# If you are building a package for yourself to use, you can use any compiler
# that works.  However if you want to run the package on a different machine 
# than you build the package, then you have to make sure that the package you 
# build is linked against a version of libstdc++ and of libc that are available 
# on that machine.  In particular, 
# we build packages linked against libstdc++ v2.9 and libc v2.1 (this means 
# the packages will work on Red Hat 6.2, as well as newer versions of Red Hat 
# and on most other Linux distributions).  In order to do that, set the 
# "USE_LIBCPP_2_9" and "USE_LIBC_2_1" environment variables before building.
# I build on Debian, and install the `libstdc++2.9-glibc2.1' package to get 
# libstdc++2.9.so.  I have to compile with GCC 2.95.4, as compiling with 
# GCC 3.0.2 yields link errors (possibly because I don't have the right 
# libstdc++ header files).  Oh yeah -- also you have to have a `libc-2.1.so' 
# file, which can be found in the `libc6' package from the potato 
# distribution, but not in the `libc6' package from the woody distribution.



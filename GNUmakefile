#
# This is a top level Makefile useful for building everything we are
# currently using on unix. -greg
#
# This Makefile invokes the python interpreter.
#
# To run this, you will need to pass the following variable
# definitions on the command line.
#
#  EGTPDIR - the location of your checked out cvs 'egtp' module 
#  EXTSRCDIR - the location of your checked out cvs 'extsrc' module 
#
# example:
#   coolmachine:~/egtp% make EGTPDIR=${HOME}/egtp EXTSRCDIR=${HOME}/extsrc
#
# $Id: GNUmakefile,v 1.7 2002/07/16 20:50:37 zooko Exp $

# For the sourcetar target to place distribution files:
DISTDIR=/var/tmp

# For the sourcetar target to create the tarball structure:
TMPDIR=/var/tmp

VERSTR="002"
PKGNAME=egtp

# GNU make is required to build this, change this or pass MAKE=gmake
# when building if it fails.
MAKE=make

# You could use the following settings to DISTUTILS parameters to build against a specific version of libstdc++ and libc.
# (But beware of C++ ABI incompatibilities, in addition to C and C++ standard library version incompatibilities...)
ifneq (${USE_LIBCPP_2_9},)
DISTUTILS_EXTRA_LINK_ARGS=-nodefaultlibs
ifneq (${USE_LIBC_2_1},)
DISTUTILS_LIBRARIES=stdc++-2-libc6.1-1-2.9.0 c-2.1.3 m-2.1.3 gcc
else
DISTUTILS_LIBRARIES=stdc++-2-libc6.1-1-2.9.0 c m gcc
endif
else
ifneq (${USE_LIBC_2_1},)
DISTUTILS_EXTRA_LINK_ARGS=-nodefaultlibs
DISTUTILS_LIBRARIES=stdc++ c-2.1.3 m-2.1.3 gcc
endif
endif

# For the source+binary target tarball:
BINUNCTARBALLNAME=$(shell echo $(PKGNAME)-$(VERSTR)-`uname`-`uname -m`.tar)
BINTARBALLNAME=$(BINUNCTARBALLNAME).gz

# The command to use to run the python interpreter (used for running
# setup.py to build external modules).
PYTHON=$(shell ${EGTPDIR}/Mstart 'echo $${PYTHON}' 2>/dev/null)
ifeq ($(strip $(PYTHON)),)
$(error "Didn't find a working Python interpreter.")
else
ifneq ($(shell if [ -f $(PYTHON) ]; then echo YEP; fi), YEP)
$(error "Didn't find a Python interpreter.")
else
ifneq ($(strip $(shell $(PYTHON) -c 'print "hello"' 2>/dev/null)), hello)
$(error "Didn't find a working Python interpreter.")
endif
endif
endif

help:
	@echo ''
	@echo 'The following targets are defined in this Makefile:'
	@echo '  all       - build and install the non-GUI related libraries & modules.'
	@echo '  clean     - clean the egtp modules.'
	@echo '  distclean - clean ALL stuff, including external libraries.'
	@echo 'Probably only for developers:'
	@echo '  sourcetar - makes a tarball suitable for distribution of just source.'
	@echo '  binarytar - makes a tarball suitable for distribution of source and binaries'
	@echo '  			 for the current platform.'
	@echo ''
	@echo 'GNU Make is required to build.  If your default "make" is not GNU,'
	@echo 'add a MAKE=gmake parameter to the command line and use GNU make,'
	@echo 'like this:'
	@echo 'gmake all MAKE=gmake'

# We do clean_bytecode here because it is too often a problem that there are old .pyc's lying around after the .py has been removed.  It takes very little time when it automatically recompiles the bytecode next time you run.
all: mencode_module pybsddb_module crypto_modules co_pyutil clean_bytecode
	@echo ''
	@echo 'All done.'
	@echo ''
	@date

# just clean the code which we wrote; not the external libraries

clean: clean_bytecode mencode_module_clean pybsddb_module_clean crypto_modules_clean
	@echo ''
	@echo 'egtp code cleaned.'
	@echo ''

# Remember to update this to include _clean targets for everything!
distclean: clean inst_berkeleydb_clean inst_cryptopp_clean setup_dirs_clean
	@echo ''
	@echo 'Dependent software and libraries cleaned.'
	@echo ''

clean_bytecode:
	@cd $(EGTPDIR)
	@find . -name "*.pyc" -print0 | xargs -0 rm -f
	@find . -name "*.pyo" -print0 | xargs -0 rm -f

bytecompile:
	cd $(EGTPDIR)
	@echo "Byte compiling .pyo files (optimized)"
	@echo "NOTE: users of python interpreters of earlier versions can not necessarily use these .pyo files.  This version is:"
	@$(PYTHON) -c 'import sys; print sys.version'
	$(PYTHON) -OO -c 'import compileall; compileall.compile_dir(".")'

stripall:
	cd $(EGTPDIR)
	@echo "stripping all unneeded symbols!"
	-find . -name "*.so" -print0 | xargs -0 strip --strip-unneeded
	-find . -name "*.a" -print0 | xargs -0 strip --strip-unneeded

binarytar: clean_bytecode all stripall
	@echo -e '\n\nCreating binary tarball.'
	@mkdir $(TMPDIR)/$(PKGNAME) || ( echo '$(TMPDIR)/$(PKGNAME)/ already exists, aborting.' ; exit 1 )
	@if [ -f $(DISTDIR)/$(BINUNCTARBALLNAME) ]; then echo '$(DISTDIR)/$(BINUNCTARBALLNAME) already exists, aborting.' ; exit 1; fi
	@ln -s ${EGTPDIR} $(TMPDIR)/$(PKGNAME)/egtp
	tar -C$(TMPDIR) --exclude-from tarexclude.txt --exclude="*.pyc" --exclude="*.pyo" --exclude ".#*" --exclude "*.rej" --exclude win32 --exclude BerkeleyDB --exclude .cvsignore --exclude CVS --exclude build --exclude "*.a" --exclude "*.o" -cvhf $(DISTDIR)/$(BINUNCTARBALLNAME) $(PKGNAME)/
	@if [ -f $(DISTDIR)/$(BINTARBALLNAME) ]; then echo '$(DISTDIR)/$(BINTARBALLNAME) already exists, aborting.' ; exit 1; fi
	( cd $(TMPDIR); gzip --best $(BINUNCTARBALLNAME) )
	@rm $(TMPDIR)/$(PKGNAME)/*
	@rmdir $(TMPDIR)/$(PKGNAME)
	@echo 'Distro tar ball created, and tagged with seconds since epoch:'
	@ls -l $(DISTDIR)/$(BINTARBALLNAME)

################ Specific targets and support targets below here ###############


unmod:
	@echo -e '\n\nMaking sure this is an un-modified checkout.'
	DIFF=`cvs diff 2>/dev/null`
	if [ "X${DIFF}" != "X" ] ; then echo there are changes from CVS -- aborting ; echo ; exit 1 ; fi

check_vars:
	@if [ "x${EGTPDIR}" = "x" -o "x${EXTSRCDIR}" = "x" ]; then echo 'You need to set your EGTPDIR and EXTSRCDIR environment variables' ; exit 1 ; fi
	@if [ ! -d ${EGTPDIR} ]; then echo 'EGTPDIR directory not found, do you need to cvs checkout egtp?' ; exit 1 ; fi
	@if [ ! -d ${EXTSRCDIR} ]; then echo 'EXTSRCDIR directory not found, do you need to cvs checkout extsrc?' ; exit 1 ; fi
	@echo Good, you appear to have valid EGTPDIR and EXTSRCDIR settings.

setup_dirs: check_vars
	@echo ======== add ${EGTPDIR}/PythonLibs to your PYTHONPATH ========
	@if [ ! -d ${EGTPDIR}/PythonLibs ]; then mkdir ${EGTPDIR}/PythonLibs ; fi

setup_dirs_clean: check_vars
	-if [ -d ${EGTPDIR}/PythonLibs ]; then rm -rf ${EGTPDIR}/PythonLibs ; fi


#
# BerkeleyDB 3.3.11
# If you don't like invoking python to get the trailing characters,
# and if your shell is bash, you can do this instead:
#	if [ "`uname -m | $(PYTHON) -c 'import sys; print sys.stdin.read()[-3:-1]'`" != "86" ]; then extraconfigureflags="--enable-posixmutexes" ; fi && \
#	FOO=`uname -m`; if [ "${FOO:$((${#FOO} - 2))}" != "86" ]; then extraconfigureflags="--enable-posixmutexes" ; fi && \

#
inst_berkeleydb: check_vars
	@echo building target inst_berkeleydb
	cd ${EXTSRCDIR} && \
	if [ -d db-3.3.11 ]; then rm -rf db-3.3.11 ; fi && \
	tar -xzf db-3.3.11.tar.gz
	cd ${EXTSRCDIR}/db-3.3.11/build_unix && \
	if [ "X$(OSTYPE)" = "Xmacos" ]; then \
	../dist/configure --prefix=${EXTSRCDIR}/BerkeleyDB --enable-posixmutexes ; \
	else \
	if [ "NONCE`uname -m | $(PYTHON) -c 'import sys; print sys.stdin.read()[-3:-1]'`" != "NONCE86" ]; then extraconfigureflags="--enable-posixmutexes" ; fi && \
	../dist/configure --prefix=${EXTSRCDIR}/BerkeleyDB ${extraconfigureflags} ; \
	fi && \
	$(MAKE) && \
	$(MAKE) install
	rm -f ${EXTSRCDIR}/BerkeleyDB/lib/*.la
	rm -f ${EXTSRCDIR}/BerkeleyDB/lib/*.so
	mv ${EXTSRCDIR}/BerkeleyDB/lib/libdb-3.3.a ${EXTSRCDIR}/BerkeleyDB/lib/libdb.a 

berkeleydb: ${EXTSRCDIR}/BerkeleyDB/lib/libdb.a
	@true

${EXTSRCDIR}/BerkeleyDB/lib/libdb.a:
	@if [ ! -f $@ ]; then \
		$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} OSTYPE=$(OSTYPE) inst_berkeleydb ; \
	fi

inst_berkeleydb_clean: check_vars
	-if [ -d ${EXTSRCDIR}/BerkeleyDB ]; then rm -rf ${EXTSRCDIR}/BerkeleyDB ; fi
	-if [ -d ${EXTSRCDIR}/db-3.3.11 ]; then rm -rf ${EXTSRCDIR}/db-3.3.11 ; fi 
	-if [ -d ${EXTSRCDIR}/db-3.1.17 ]; then rm -rf ${EXTSRCDIR}/db-3.1.17 ; fi 
	-if [ -d ${EXTSRCDIR}/db-3.1.14 ]; then rm -rf ${EXTSRCDIR}/db-3.1.14 ; fi 
	-if [ -d ${EXTSRCDIR}/bsddb3 ]; then rm -rf ${EXTSRCDIR}/bsddb3 ; fi 

#
# the pybsddb berkeleydb 3.3.0 python module (http://sourceforge.net/projects/pybsddb/)
#

# I echo "yes" to setup because on cf.sf.net's FreeBSD 4.3-RELEASE build box the python2.0 executable has an old bsddb statically linked in which causes setup.py to put up a warning and a "yes/no to continue".
#patch -p0 <../bsddb3-3.3.0-moreargs.patch && \
#echo yes | $(PYTHON) setup.py --libraries="$(DISTUTILS_LIBRARIES)" --library_dirs="$(DISTUTILS_LIBRARY_DIRS)" --include_dirs="$(DISTUTILS_INCLUDE_DIRS)" --extra_compile_args="$(DISTUTILS_EXTRA_COMPILE_ARGS)" --extra_link_args="$(DISTUTILS_EXTRA_LINK_ARGS)" build_ext --inplace --berkeley-db=${EXTSRCDIR}/BerkeleyDB
#patch -p0 <../bsddb3-3.3.0-moreargs.patch && \

inst_pybsddb: berkeleydb 
	@echo building target inst_pybsddb
	@cd ${EXTSRCDIR} && \
	if [ -d bsddb3-3.3.0 ]; then rm -rf bsddb3-3.3.0 ; fi && \
	tar -xzf bsddb3-3.3.0.tar.gz && \
	cd ${EXTSRCDIR}/bsddb3-3.3.0 && \
	patch -p1 <../bsddb3-3.3.0-set_flags-fix.patch && \
	patch -p0 <../bsddb3-3.3.0-moreargs.patch && \
	echo yes | $(PYTHON) setup.py --libraries="$(DISTUTILS_LIBRARIES)" --library_dirs="$(DISTUTILS_LIBRARY_DIRS)" --include_dirs="$(DISTUTILS_INCLUDE_DIRS)" --extra_compile_args="$(DISTUTILS_EXTRA_COMPILE_ARGS)" --extra_link_args="$(DISTUTILS_EXTRA_LINK_ARGS)" --berkeley-db=${EXTSRCDIR}/BerkeleyDB build_ext --inplace
	-if [ ! -d ${EGTPDIR}/PythonLibs ]; then mkdir ${EGTPDIR}/PythonLibs ; fi
	-if [ ! -d ${EGTPDIR}/PythonLibs/bsddb3 ]; then mkdir ${EGTPDIR}/PythonLibs/bsddb3 ; fi
	-cp ${EXTSRCDIR}/bsddb3-3.3.0/bsddb3/* ${EGTPDIR}/PythonLibs/bsddb3
	-rm -f ${EGTPDIR}/common/bsddb3/__init__.pyc ${EGTPDIR}/common/bsddb3/__init__.pyo

inst_pybsddb_clean:
	@echo building target inst_pybsddb_clean
	@cd ${EXTSRCDIR} && \
	rm -rf bsddb3-3.3.0 && \
	rm -rf db-3-3.3.11 

${EGTPDIR}/PythonLibs/bsddb3/_db.so:
	@if [ ! -f $@ ]; then \
		$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} OSTYPE=${OSTYPE} inst_pybsddb ; \
	fi

pybsddb_module: bsddb3_obsolete_module_delete check_vars ${EGTPDIR}/PythonLibs/bsddb3/_db.so
	@true

# I echo "yes" to setup because on cf.sf.net's FreeBSD 4.3-RELEASE build box the python2.0 executable has an old bsddb statically linked in which causes setup.py to put up a warning and a "yes/no to continue".
pybsddb_module_clean: check_vars
	-rm -rf ${EGTPDIR}/PythonLibs/bsddb3
	-if [ -d ${EXTSRCDIR}/bsddb3-3.3.0 ]; then \
		(cd ${EXTSRCDIR}/bsddb3-3.3.0 ; echo yes | $(PYTHON) setup.py clean --berkeley-db=${EXTSRCDIR}/BerkeleyDB ; rm -f bsddb3/_db.so) ; \
	fi


# This target removes the now-obsolete common/bsddb3 directory,
# which can cause problems if it is allowed to coexist with
# the newer pybsddb module.
bsddb3_obsolete_module_delete:
	@-if [ -d ${EGTPDIR}/common/bsddb3 ]; then echo "Removing obsolete directory ${EGTPDIR}/common/bsddb3"; rm -rf ${EGTPDIR}/common/bsddb3; fi

#
# our faster mencode module
#
mencode_module: check_vars setup_dirs
	@echo building target mencode_module
	cd ${EGTPDIR}/common/c_mencode && $(PYTHON) setup.py build_ext --inplace

mencode_module_clean: check_vars
	-rm -f ${EGTPDIR}/common/c_mencode/*.so
	-cd ${EGTPDIR}/common/c_mencode && $(PYTHON) setup.py clean && rm -rf build

#
# Crypto++ 3.2 library
#
inst_cryptopp_32: check_vars
	@echo building target inst_cryptopp
	@cd ${EXTSRCDIR} && \
	if [ ! -d cryptopp ]; then mkdir cryptopp ; fi && \
	cd cryptopp && \
	unzip -o -a ../crypto32.zip && \
	patch <../crypto32-endian.patch && \
	patch <../crypto32-makefile.patch && \
	echo Checking gcc version && \
	if [ "x`gcc --version 2>&1 | head -1 | grep egcs`" != "x" ]; then \
		echo 'Removing -fpermissive compiler flag due to egcs' ; \
		sed -e 's/-fpermissive//' <Makefile >Makefile.evil ; \
		mv Makefile Makefile.pre-evil ; \
		cp Makefile.evil Makefile ; \
	fi && \
	$(MAKE) libcryptopp.a

#
# Crypto++ 4.0 library
#
inst_cryptopp_40: check_vars
	@echo building target inst_cryptopp
	@cd ${EXTSRCDIR} && \
	if [ ! -d cryptopp ]; then mkdir cryptopp ; fi && \
	cd cryptopp && \
	unzip -o -a ../crypto40.zip && \
	patch <../crypto40-makefile.patch && \
	patch <../crypto40-incl.patch && \
	if [ "X$(OSTYPE)" = "Xmacos" ]; then \
	patch <../iterhash.h.patch && \
	patch <../iterhash.cpp.patch ; \
	fi && \
	echo Checking gcc version && \
	if [ "x`gcc --version 2>&1 | head -1 | grep egcs`" != "x" ]; then \
		echo 'Removing -fpermissive compiler flag due to egcs' ; \
		sed -e 's/-fpermissive//' <Makefile >Makefile.evil ; \
		mv Makefile Makefile.pre-evil ; \
		cp Makefile.evil Makefile ; \
	fi && \
	$(MAKE) libcryptopp.a

#
# Crypto++ 4.1 library
#
inst_cryptopp_41: check_vars
	@echo building target inst_cryptopp
	@cd ${EXTSRCDIR} && \
	if [ ! -d cryptopp ]; then mkdir cryptopp ; fi && \
	cd cryptopp && \
	unzip -o -a ../crypto41.zip && \
	patch <../crypto41-gcc3.patch && \
	patch <../crypto41-make.patch && \
	patch <../crypto41-OpenBSD.patch && \
	patch <../crypto41-fPIC.patch && \
	patch <../crypto41-MacOSX-GNUmakefile.patch && \
	if [ "X$(OSTYPE)" = "Xmacos" ]; then \
	patch <../iterhash.h.patch && \
	patch <../iterhash.cpp.patch ; \
	fi && \
	echo Checking gcc version && \
	if [ "x`gcc --version 2>&1 | head -1 | grep egcs`" != "x" ]; then \
		echo 'Removing -fpermissive compiler flag due to egcs' ; \
		sed -e 's/-fpermissive//' <GNUmakefile >GNUmakefile.evil ; \
		mv GNUmakefile GNUmakefile.pre-evil ; \
		cp GNUmakefile.evil GNUmakefile ; \
	fi && \
	$(MAKE) libcryptopp.a

#
# Crypto++ 4.2 library
#
inst_cryptopp_42: check_vars
	@echo building target inst_cryptopp
	@cd ${EXTSRCDIR} && \
	if [ ! -d cryptopp ]; then mkdir cryptopp ; fi && \
	cd cryptopp && \
	unzip -o -a ../crypto42.zip && \
	patch <../crypto42-limitedbuild-GNUmakefile.patch && \
	patch < ../crypto42-ndebug-GNUmakefile.patch && \
	patch < ../crypto42-ndebug2-GNUmakefile.patch && \
	patch < ../crypto42-gcc31errs.patch && \
	patch < ../crypto42-gcc31warns.patch && \
	echo Checking gcc version && \
	if [ "x`gcc --version 2>&1 | head -1 | grep egcs`" != "x" ]; then \
		echo 'Removing -fpermissive compiler flag due to egcs' ; \
		sed -e 's/-fpermissive//' <GNUmakefile >GNUmakefile.evil ; \
		mv GNUmakefile GNUmakefile.pre-evil ; \
		cp GNUmakefile.evil GNUmakefile ; \
	fi && \
	$(MAKE) libcryptopp.a

cryptopp: ${EXTSRCDIR}/cryptopp/libcryptopp.a
	@true

${EXTSRCDIR}/cryptopp/libcryptopp.a:
	@if [ ! -f $@ ]; then \
		if [ "X${USE_CRYPTOPP_32}" != "X" ]; then \
			$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} inst_cryptopp_32 ; \
		else \
			if [ "X${USE_CRYPTOPP_40}" != "X" ]; then \
				$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} OSTYPE=$(OSTYPE) inst_cryptopp_40 ; \
			else \
				if [ "X${USE_CRYPTOPP_41}" != "X" ]; then \
					$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} OSTYPE=$(OSTYPE) inst_cryptopp_41 ; \
				else \
					$(MAKE) EXTSRCDIR=${EXTSRCDIR} EGTPDIR=${EGTPDIR} OSTYPE=$(OSTYPE) inst_cryptopp_42 ; \
				fi \
			fi \
		fi \
	fi

inst_cryptopp_clean:
	-CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ -d ${EXTSRCDIR}/crypto32 ]; then rm -rf ${EXTSRCDIR}/crypto32 ; fi
	-CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ -d ${EXTSRCDIR}/crypto40 ]; then rm -rf ${EXTSRCDIR}/crypto40 ; fi
	-CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ -d ${EXTSRCDIR}/crypto41 ]; then rm -rf ${EXTSRCDIR}/crypto41 ; fi
	-CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ -d ${EXTSRCDIR}/crypto42 ]; then rm -rf ${EXTSRCDIR}/crypto42 ; fi
	-CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ -d ${EXTSRCDIR}/cryptopp ]; then rm -rf ${EXTSRCDIR}/cryptopp ; fi

#
# our crypto++ based libraries
#
crypto_modules: check_vars cryptopp
	@echo building target crypto_modules
	@cd ${EGTPDIR}/common/crypto/Python && \
	CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ "X${USE_CRYPTOPP_32}" != "X" ]; then \
		export CRYPTOPP_VERSION="3.2" ; \
	else \
		if [ "X${USE_CRYPTOPP_40}" != "X" ]; then \
			export CRYPTOPP_VERSION="4.0" ; \
		else \
			if [ "X${USE_CRYPTOPP_41}" != "X" ]; then \
				export CRYPTOPP_VERSION="4.1" ; \
			else \
				export CRYPTOPP_VERSION="4.2" ; \
			fi \
		fi \
	fi && \
	$(PYTHON) setup.py --libraries="$(DISTUTILS_LIBRARIES)" --library_dirs="$(DISTUTILS_LIBRARY_DIRS)" --include_dirs="$(DISTUTILS_INCLUDE_DIRS)" --extra_compile_args="$(DISTUTILS_EXTRA_COMPILE_ARGS)" --extra_link_args="$(DISTUTILS_EXTRA_LINK_ARGS)" build_ext --inplace
	@echo ======== add ${EGTPDIR}/common/crypto/Python to your PYTHONPATH ========

crypto_modules_clean:
	-cd ${EGTPDIR}/common/crypto/Python && \
	CRYPTOPP_DIR=${EXTSRCDIR}/cryptopp && export CRYPTOPP_DIR && \
	if [ "X${USE_CRYPTOPP_32}" != "X" ]; then \
		export CRYPTOPP_VERSION="3.2" ; \
	else \
		if [ "X${USE_CRYPTOPP_40}" != "X" ]; then \
			export CRYPTOPP_VERSION="4.0" ; \
		else \
			if [ "X${USE_CRYPTOPP_41}" != "X" ]; then \
				export CRYPTOPP_VERSION="4.1" ; \
			else \
				export CRYPTOPP_VERSION="4.2" ; \
			fi \
		fi \
	fi && \
	$(PYTHON) setup.py clean && \
	rm -rf build && \
	if [ -f evilcryptopp.so ]; then rm -f evilcryptopp.so ; fi

# co_pyutil 

co_pyutil:
	@cd ${EGTPDIR}/PythonLibs && \
	touch ${HOME}/.cvspass && \
	if [ "`grep anonymous@cvs.pyutil ${HOME}/.cvspass`" = "" ]; then \
		echo ":pserver:anonymous@cvs.pyutil.sourceforge.net:/cvsroot/pyutil A" >>${HOME}/.cvspass ; \
	fi && \
	if [ -d pyutil ]; then \
		(cd pyutil && cvs -z3 -d:pserver:anonymous@cvs.pyutil.sourceforge.net:/cvsroot/pyutil up -Pd ) ; \
	else \
		cvs -z3 -d:pserver:anonymous@cvs.pyutil.sourceforge.net:/cvsroot/pyutil co -P pyutil ; \
	fi



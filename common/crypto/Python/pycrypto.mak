# Microsoft Developer Studio Generated NMAKE File, Based on pycrypto.dsp
!IF "$(CFG)" == ""
CFG=pycrypto - Win32 Release
!MESSAGE No configuration specified. Defaulting to pycrypto - Win32 Release.
!ENDIF 

!IF "$(CFG)" != "pycrypto - Win32 Release"
!MESSAGE Invalid configuration "$(CFG)" specified.
!MESSAGE You can specify a configuration when running NMAKE
!MESSAGE by defining the macro CFG on the command line. For example:
!MESSAGE 
!MESSAGE NMAKE /f "pycrypto.mak" CFG="pycrypto - Win32 Release"
!MESSAGE 
!MESSAGE Possible choices for configuration are:
!MESSAGE 
!MESSAGE "pycrypto - Win32 Release" (based on "Win32 (x86) Dynamic-Link Library")
!MESSAGE 
!ERROR An invalid configuration is specified.
!ENDIF 

!IF "$(OS)" == "Windows_NT"
NULL=
!ELSE 
NULL=nul
!ENDIF 

CPP=cl.exe
MTL=midl.exe
RSC=rc.exe
OUTDIR=.
INTDIR=.
# Begin Custom Macros
OutDir=.
# End Custom Macros

ALL : "$(OUTDIR)\evilcryptopp.pyd"


CLEAN :
	-@erase "$(INTDIR)\evilcryptopp.obj"
	-@erase "$(INTDIR)\modval.obj"
	-@erase "$(INTDIR)\randsource.obj"
	-@erase "$(INTDIR)\randsource_methods.obj"
	-@erase "$(INTDIR)\tripledescbc.obj"
	-@erase "$(INTDIR)\vc60.idb"
	-@erase "$(INTDIR)\wrappedrsa.obj"
	-@erase "$(OUTDIR)\evilcryptopp.exp"
	-@erase "$(OUTDIR)\evilcryptopp.pyd"

BSC32=bscmake.exe
BSC32_FLAGS=/nologo /o"$(OUTDIR)\pycrypto.bsc" 
BSC32_SBRS= \
	
LINK32=link.exe
LINK32_FLAGS=kernel32.lib user32.lib gdi32.lib winspool.lib comdlg32.lib advapi32.lib shell32.lib ole32.lib oleaut32.lib uuid.lib odbc32.lib odbccp32.lib cryptlib-mojo.lib python16.lib /nologo /dll /pdb:none /machine:I386 /def:".\evilcryptopp.def" /out:"$(OUTDIR)\evilcryptopp.pyd" /implib:"$(OUTDIR)\evilcryptopp.lib" /libpath:"..\..\..\..\extsrcwin\crypto32\release" /libpath:"c:\python20\libs" 
DEF_FILE= \
	".\evilcryptopp.def"
LINK32_OBJS= \
	"$(INTDIR)\evilcryptopp.obj" \
	"$(INTDIR)\modval.obj" \
	"$(INTDIR)\randsource.obj" \
	"$(INTDIR)\randsource_methods.obj" \
	"$(INTDIR)\tripledescbc.obj" \
	"$(INTDIR)\wrappedrsa.obj"

"$(OUTDIR)\evilcryptopp.pyd" : "$(OUTDIR)" $(DEF_FILE) $(LINK32_OBJS)
    $(LINK32) @<<
  $(LINK32_FLAGS) $(LINK32_OBJS)
<<

CPP_PROJ=/nologo /MD /W3 /GX /O2 /I "..\..\..\..\extsrcwin\crypto32" /I "c:\python20\include" /I "..\\" /D "NDEBUG" /D "WIN32" /D "_WINDOWS" /D "_MBCS" /D "_USRDLL" /D "PYCRYPTO_EXPORTS" /D "PYTHON_MODULE" /D "HAVE_STDLIB_H" /FD /c 

.c.obj::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

.cpp.obj::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

.cxx.obj::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

.c.sbr::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

.cpp.sbr::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

.cxx.sbr::
   $(CPP) @<<
   $(CPP_PROJ) $< 
<<

MTL_PROJ=/nologo /D "NDEBUG" /mktyplib203 /win32 

!IF "$(NO_EXTERNAL_DEPS)" != "1"
!IF EXISTS("pycrypto.dep")
!INCLUDE "pycrypto.dep"
!ELSE 
!MESSAGE Warning: cannot find "pycrypto.dep"
!ENDIF 
!ENDIF 


!IF "$(CFG)" == "pycrypto - Win32 Release"
SOURCE=.\evilcryptopp.cpp

"$(INTDIR)\evilcryptopp.obj" : $(SOURCE) "$(INTDIR)"


SOURCE=.\modval.cpp

"$(INTDIR)\modval.obj" : $(SOURCE) "$(INTDIR)"


SOURCE=.\randsource.cpp

"$(INTDIR)\randsource.obj" : $(SOURCE) "$(INTDIR)"


SOURCE=..\randsource_methods.cpp

"$(INTDIR)\randsource_methods.obj" : $(SOURCE) "$(INTDIR)"
	$(CPP) $(CPP_PROJ) $(SOURCE)


SOURCE=.\tripledescbc.cpp

"$(INTDIR)\tripledescbc.obj" : $(SOURCE) "$(INTDIR)"


SOURCE=..\wrappedrsa.cpp

"$(INTDIR)\wrappedrsa.obj" : $(SOURCE) "$(INTDIR)"
	$(CPP) $(CPP_PROJ) $(SOURCE)



!ENDIF 


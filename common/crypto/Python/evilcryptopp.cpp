//
// A module that merges randsource and modval into one external
// module to keep dynamic linking happy.
//
// $Id: evilcryptopp.cpp,v 1.1 2002/01/29 20:07:07 zooko Exp $


#include "integer.h"


#define MAX_METHODS 40

#ifndef WIN32
#ifdef __cplusplus
extern "C"
{
#endif
#endif // ifndef WIN32

#include "Python.h"

  extern PyMethodDef randsource_functions[];
  extern PyMethodDef modval_module_functions[];
  extern PyMethodDef tripledescbc_functions[];

#ifndef __APPLE__
  extern char* module_doc;
#endif
  extern char* randsource_doc;
  extern char* tripledescbc_doc;

  
  extern PyObject *ModValError;
  extern PyObject *TripleDESCBCError;

#ifndef WIN32
#ifdef __cplusplus
}
#endif
#endif // ifndef WIN32

// #include "randsource.cc"
//include "modval.cc"
//include "tripledescbc.cc"


/*
 *  Copy the python function definitions from srcfuncs into the
 *  destfuncs array starting at offset destoffset, not to exceed
 *  destarraylen.  Returns the new destoffset value (to be passed to a
 *  subsequent call to copy_py_func_defs).
 *
 *  If the return value is unchanged from destoffset, srcfuncs was
 *  either empty or there was no more room  in destfuncs.
 */
int copy_py_func_defs(struct PyMethodDef *destfuncs, int destoffset, int destarraylen, char* newnameprefix, struct PyMethodDef *srcfuncs)
{
        int idx = 0;  // index into srcfuncs
        while (destoffset < destarraylen && srcfuncs[idx].ml_name != NULL) 
        {
                int newnamelen;
                char* newname;

                memcpy((void*)(destfuncs+destoffset), (void*)(srcfuncs+idx), sizeof(struct PyMethodDef));

                // add newnameprefix to the function name
                newnamelen = strlen(destfuncs[destoffset].ml_name) + strlen(newnameprefix);
                newname = (char*)malloc(newnamelen+1);
                strncpy(newname, newnameprefix, newnamelen);
                strncat(newname, destfuncs[destoffset].ml_name, newnamelen-strlen(newname));
                destfuncs[destoffset].ml_name = newname;

                ++idx;
                ++destoffset;
        }

        return destoffset;
} /* copy_py_func_defs() */

#ifdef __cplusplus
extern "C"
{
#endif
DL_EXPORT(void)
initevilcryptopp()
{
        PyObject *m, *d;

        /* XXX this function is a quick hack but it'll suffice for now
         * until we build everything in one binary */
        static struct PyMethodDef allfunctions[MAX_METHODS];
        static char ourdoc[] =
            "The evilcryptopp module contains modval, randsource and tripledescbc\n"
            "all merged into a single C module for dynamic linking reasons\n\n"
            "The original doc strings are available:\n"
            "  _modval_doc\n  _randsource_doc\n  _tripledescbc_doc\n\n"
            "All methods from each module have been prefixed with _modulename_\n\n"
            "You really shouldn't use this module; use the .py wrappers that\n"
            "emulate the modval, randsource and tripledescbc interfaces.\n";
        int total;

        /* Create a module containing all modval and randsource
         * functions; assuming no name collisions -greg */
        total = 0;
        total = copy_py_func_defs(allfunctions, total, MAX_METHODS, "_randsource_", randsource_functions);
        total = copy_py_func_defs(allfunctions, total, MAX_METHODS, "_modval_", modval_module_functions);
        total = copy_py_func_defs(allfunctions, total, MAX_METHODS, "_tripledescbc_", tripledescbc_functions);

        m = Py_InitModule3("evilcryptopp", allfunctions, ourdoc);

        d = PyModule_GetDict(m);
        ModValError = PyErr_NewException("evilcryptopp.ModValError", NULL, NULL);
        TripleDESCBCError = PyErr_NewException("evilcryptopp.TripleDESCBCError", NULL, NULL);

        // errors
        PyDict_SetItemString(d, "ModValError", ModValError);
        PyDict_SetItemString(d, "TripleDESCBCError", TripleDESCBCError);

        // original doc string
	#ifdef __APPLE__
        PyDict_SetItemString(d, "_modval_doc", PyString_FromString(""));
	#else
        PyDict_SetItemString(d, "_modval_doc", PyString_FromString(module_doc));
	#endif
        PyDict_SetItemString(d, "_randsource_doc", PyString_FromString(randsource_doc));
        PyDict_SetItemString(d, "_tripledescbc_doc", PyString_FromString(tripledescbc_doc));

#ifdef CRYPTOPP_42
        PyDict_SetItemString(d, "cryptopp_version", PyString_FromString("4.2"));
#else
#ifdef CRYPTOPP_41
        PyDict_SetItemString(d, "cryptopp_version", PyString_FromString("4.1"));
#else
#ifdef CRYPTOPP_40
        PyDict_SetItemString(d, "cryptopp_version", PyString_FromString("4.0"));
#else
        PyDict_SetItemString(d, "cryptopp_version", PyString_FromString("3.2"));
#endif
#endif
#endif
}
#ifdef __cplusplus
}
#endif

#include "cryptlib.h"  // including this prevents a double-link error on windows -greg

//extern "C"
//{
#include <Python.h>
//}


typedef unsigned char byte; // Copied from Crypto++'s "config.h" --Zooko 2000/05/01

#define xdelete(p) delete (p); p = NULL
#define xdeletear(p) delete[] (p); p = NULL

// Declarations of randsource methods.
extern "C"
{
extern void randsource_add(const unsigned char *data, unsigned int amount, unsigned int entropybits);

extern int randsource_get(unsigned char *data, unsigned int amount);
}


typedef struct
{
	PyObject_HEAD
} randsource;

static void randsource_delete(randsource *self);

static PyObject *exposed_randsource_ready(randsource *self, PyObject *args);

static PyObject *exposed_randsource_get(randsource *self, PyObject *args);

static PyObject *exposed_randsource_add(randsource *self, PyObject *args);

static PyObject *randsource_getattr(randsource *self, char* name);

statichere PyTypeObject randsource_type = {
        PyObject_HEAD_INIT(&PyType_Type)
        0,                        /*ob_size*/
        "randsource",                  /*tp_name*/
        sizeof(randsource),        /*tp_size*/
        0,                        /*tp_itemsize*/
        /* methods */
        (destructor)randsource_delete,  /*tp_dealloc*/
        0,                        /*tp_print*/
        (getattrfunc)randsource_getattr, /*tp_getattr*/
        0,                        /*tp_setattr*/
        0,                        /*tp_compare*/
        0,                        /*tp_repr*/
        0,                        /*tp_as_number*/
        0,                        /*tp_as_sequence*/
        0,                        /*tp_as_mapping*/
        0,                        /*tp_hash*/
        0,                        /*tp_call*/
        0,                        /*tp_str*/
        0,                        /*tp_getattro*/
        0,                        /*tp_setattro*/
        0,                        /*tp_as_buffer*/
        0,                        /*tp_xxx4*/
        0,                        /*tp_doc*/
};

static PyMethodDef randsource_ms[] = {
    {NULL, NULL} /* sentinel */
};

static PyObject *randsource_getattr(randsource *self, char* name)
{
	return Py_FindMethod(randsource_ms, (PyObject *)self, name);
}

static void randsource_delete(randsource *self) {
	if(self != NULL) {
		PyMem_DEL(self);
	}
}

static PyObject *exposed_randsource_add(randsource *self, PyObject *args) {
	byte *bytes;
	unsigned int numbytes;
	unsigned int entropybits = 0;
	if(!PyArg_ParseTuple(args, "s#|i", &bytes, &numbytes, &entropybits)) {
		PyErr_SetString(PyExc_RuntimeError, "bad argument types");
		return NULL;
	}
	if(entropybits > numbytes * 8) {
		PyErr_SetString(PyExc_RuntimeError, "can't have more bits of entropy than bits of input");
		return NULL;
	}
	randsource_add(bytes, numbytes, entropybits);
	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *exposed_randsource_get(randsource *self, PyObject *args) {
	unsigned int numbytes;
	if(!PyArg_ParseTuple(args, "i", &numbytes)) {
		PyErr_SetString(PyExc_RuntimeError, "bad argument types");
		return NULL;
	}
	byte *bytes = new byte[numbytes];
	if(!randsource_get(bytes, numbytes)) {
		xdeletear(bytes);
		PyErr_SetString(PyExc_RuntimeError, "not enough entropy collected");
		return NULL;
	}
	PyObject *result = Py_BuildValue("s#", bytes, numbytes);
	if(result == NULL)
	{
		xdeletear(bytes);
		PyErr_SetString(PyExc_MemoryError, "Can't allocate memory to generate random bytes");
		return NULL;
	}
	xdeletear(bytes);
	return result;
}

static PyObject *exposed_randsource_ready(randsource *self, PyObject *args) {
	byte bytes[1];
	if (!randsource_get(bytes, 1)) {
		return Py_BuildValue("i", 0);
	}

	return Py_BuildValue("i", 1);
}

  

PyMethodDef randsource_functions[] = {
	{"get", (PyCFunction)exposed_randsource_get, METH_VARARGS, 
	 "Returns a random string.\n"
	 "Takes a string length in bytes as the parameter."
	}, 
	{"add", (PyCFunction)exposed_randsource_add, METH_VARARGS, 
	 "Incorporates new entropy into the pool.\n"
	 "Takes a random string and optionally an estimated number of bits of\n"
	 "entropy in that string. It's a good idea to estimate conservatively.\n"
	 "The default estimate is zero."
	}, 
	{"ready", (PyCFunction)exposed_randsource_ready, METH_VARARGS,
	 "Return `true' if and only if the random pool has been initialized \n"
	 "with enough randomness and is ready to produce random numbers.\n"
	},
	{NULL, NULL} /* Sentinel */
};

char* randsource_doc =
"This class handles generation of random numbers and incorporation of\n"
"new entropy in a cryptographically secure manner.\n"
"\n"
"Available class methods - \n"
"get - returns a random string\n"
"add - incorporates new entropy into the pool\n"
"ready - return `true' if and only if the pool is prepared to produce\n"
"    random numbers";

/* Initialize this module. */

extern "C"
{
DL_EXPORT(void)
initrandsource()
{
	Py_InitModule3("randsource", randsource_functions, randsource_doc);
}
}


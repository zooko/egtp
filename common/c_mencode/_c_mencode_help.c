/*
 * mencode.py helper functions written in C for speed
 * 
 * $Id: _c_mencode_help.c,v 1.2 2002/06/25 03:42:29 zooko Exp $
 */

#include <stdlib.h>
#include <string.h>
#include <stdio.h> /* debugging */

#ifdef __cplusplus
extern "C" {
#endif
#include <Python.h>
#ifdef __cplusplus
}
#endif


#define RETURN_IF_EXC(ret)    if (!ret) { Py_XDECREF(owrite_method); return NULL; }


static PyObject* MencodeError;

static PyObject *colon_tup_const, *close_paren_tup_const, *str_tup_const, *dict_tup_const;

static PyObject *encoder_dict;

// need this prototype
static PyObject *real_encode_io(PyObject *data, PyObject *output);


static PyObject *real_encode_string(PyObject *data, PyObject *output)
{
	/* XXX Hm.  It would be nice to build the whole thing in C land and then spew it in a single call to Python land...   --Zooko 2001-11-28 */
    PyObject *ret, *str, *length = NULL;
    PyObject *owrite_method;
    PyObject *excval;

    owrite_method = PyObject_GetAttrString(output, "write");
    if (!owrite_method || !PyCallable_Check(owrite_method)) {
	    excval = Py_BuildValue("(is)", 0, "output object must have a callable write method");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
	    Py_XDECREF(owrite_method);
	    return NULL;
    }

    //    result.write('(6:string')
    ret = PyObject_CallObject(owrite_method, str_tup_const);
    RETURN_IF_EXC(ret);
    Py_DECREF(ret);
 
    //    result.write(str(len(data)))
    length = PyInt_FromLong((long)PyObject_Length(data));
    str = PyObject_Str(length);
    ret = PyObject_CallFunction(owrite_method, "S", str);
    Py_DECREF(length);
    Py_DECREF(str);
    RETURN_IF_EXC(ret);
    Py_DECREF(ret);
    
    // result.write(':')
    ret = PyObject_CallObject(owrite_method, colon_tup_const);
    RETURN_IF_EXC(ret);
    Py_DECREF(ret);
    
    // result.write(str(data))
    ret = PyObject_CallFunction(owrite_method, "S", data);
    RETURN_IF_EXC(ret);
    Py_DECREF(ret);
    
    // result.write(')')
    ret = PyObject_CallObject(owrite_method, close_paren_tup_const);
    RETURN_IF_EXC(ret);
    Py_DECREF(ret);
    
    Py_XDECREF(owrite_method);

    Py_INCREF(Py_None);
    return Py_None;
} 

static PyObject *encode_string(PyObject *self, PyObject *args)
{
    PyObject *data, *output = NULL;
    PyObject *excval;
    
    if (!PyArg_ParseTuple(args, "OO:encode_string", &data, &output)) {
	    excval = Py_BuildValue("(is)", 0, "expected two python objects as parameters");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
        return NULL;
    }
    return real_encode_string(data, output);
}

static PyObject *real_encode_dict(PyObject *data, PyObject *output)
{
	PyObject *keys, *key, *ret;
	int i, keylen;
	PyObject *owrite_method;
	PyObject *excval;

	owrite_method = PyObject_GetAttrString(output, "write");
	if (!owrite_method || !PyCallable_Check(owrite_method)) {
		excval = Py_BuildValue("(is)", 0, "output object must have a callable write method");
		if (excval != NULL) {
			PyErr_SetObject(PyExc_ValueError, excval);
			Py_DECREF(excval);
		}
		Py_XDECREF(owrite_method);
		return NULL;
	}

	// result.write('(4:dict')
	ret = PyObject_CallObject(owrite_method, dict_tup_const);
	RETURN_IF_EXC(ret);
	Py_DECREF(ret);

	// keys = data.keys()
	keys = PyDict_Keys(data);

	// keys.sort()
	// XXX FIXME bad!  this depends on the python implementations cross type comparison (string > integer or long)
	if (PyList_Sort(keys) != 0) {
		excval = Py_BuildValue("(is)", 0, "PyList_Sort failed [returned non zero]");
		if (excval != NULL) {
			PyErr_SetObject(MencodeError, excval);
			Py_DECREF(excval);
		}
		Py_DECREF(keys);
		Py_DECREF(owrite_method);
		return NULL;
	}

	keylen = PyList_Size(keys);
	// for key in keys:
	for (i = 0; i < keylen; i++) {
		key = PyList_GetItem(keys, i);
		//     if type(key) not in (types.StringType, types.IntType, types.LongType):
		// TODO support BufferType in the future
		if (!PyString_Check(key) && !PyInt_Check(key) && !PyLong_Check(key)) {
			Py_DECREF(keys);
			// it would be nice if this exception included the key we tried to encode...
			excval = Py_BuildValue("(is)", 0, "mencoded dictionary keys must be strings or numbers");
			if (excval != NULL) {
				PyErr_SetObject(MencodeError, excval);
				Py_DECREF(excval);
			}
			Py_DECREF(owrite_method);
			return NULL;
		}
		//     encode_io(key, result)
		if (real_encode_io(key, output) == NULL) {
			Py_DECREF(keys);
			Py_DECREF(owrite_method);
			return NULL;
		}
		//     encode_io(data[key], result)
		if (real_encode_io(PyDict_GetItem(data, key), output) == NULL) {
			Py_DECREF(keys);
			Py_DECREF(owrite_method);
			return NULL;
		}
	}

	Py_DECREF(keys);

	// result.write(')')
	ret = PyObject_CallObject(owrite_method, close_paren_tup_const);
	RETURN_IF_EXC(ret);
	Py_DECREF(ret);

	Py_XDECREF(owrite_method);

	Py_INCREF(Py_None);
	return Py_None;
} 


static PyObject *encode_dict(PyObject *self, PyObject *args)
{
    PyObject *data, *output;
    PyObject *excval;
    
    if (!PyArg_ParseTuple(args, "OO:encode_dict", &data, &output)) {
	    excval = Py_BuildValue("(is)", 0, "expected two python objects as parameters");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    
    return real_encode_dict(data, output);
}


static PyObject *real_encode_io(PyObject *data, PyObject *output)
{
	PyObject *type, *func, *tup, *ret = NULL;
	PyObject *excval;
	if (PyString_Check(data)) {
		/* TODO accept buffer objects */
		return real_encode_string(data, output);
	}
	else if (PyDict_Check(data)) {
		return real_encode_dict(data, output);
	}
	else {
		type = PyObject_Type(data);
		if (type == NULL)
			return NULL;

		func = PyDict_GetItem(encoder_dict, type);   /* borrowed reference to func */
		/* printf("type: %p, func: %p\n", type, func); */
		Py_DECREF(type);
		if (func == NULL) {
			/* TODO include a reference to data in this error */
			excval = Py_BuildValue("(is)", 0, "encoder_dict did not contain an encoding function for data");
			if (excval != NULL) {
				PyErr_SetObject(MencodeError, excval);
				Py_DECREF(excval);
			}
			return NULL;
		}
		tup = PyTuple_New(2);
		if (tup == NULL)
			return NULL;
		Py_INCREF(data);
		Py_INCREF(output);
		PyTuple_SET_ITEM(tup, 0, data);
		PyTuple_SET_ITEM(tup, 1, output);
		ret =  PyObject_CallObject(func, tup);
		Py_DECREF(tup);
		return ret;
	}
}

static PyObject *encode_io(PyObject *self, PyObject *args)
{
    PyObject *data, *output;
    PyObject *excval;
    if (!PyArg_ParseTuple(args, "OO:encode_io", &data, &output)) {
	    excval = Py_BuildValue("(is)", 0, "expected two python objects as parameters");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    return real_encode_io(data, output);
}


/* @param a python string object and an integer index as python parameters */
/* @returns tuple of a python string and an ending index into its string parameter */
static PyObject *decode_raw_string(PyObject *self, PyObject *args)
{
    PyObject *dataobj = NULL;
    int dataptrlen;
    int index, strlength, dataend;
    char *dataptr, *digitptr, *colonptr;
    PyObject *excval;

    /*printf("args = %p\n", args);*/
    if (!PyArg_ParseTuple(args, "Oi:decode_raw_string", &dataobj, &index)) {
	    excval = Py_BuildValue("(is)", 0, "expected a string and an integer as parameters");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    /*printf("dataobj = %p, index = %d\n", dataobj, index);*/

    if (index < 0) {
	    excval = Py_BuildValue("(is)", 0, "index must be a non-negative integer");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_ValueError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    if (PyString_Check(dataobj)) {
        /*PyString_AsStringAndSize(dataobj, &dataptr, &dataptrlen); */   /* python 1.5.2 doesn't have this function */
        dataptrlen = PyString_Size(dataobj);
        dataptr = PyString_AsString(dataobj);

        if (!dataptr) {
		excval = Py_BuildValue("(is)", 0, "first parameter was not a python object?");
		if (excval != NULL) {
			PyErr_SetObject(PyExc_TypeError, excval);
			Py_DECREF(excval);
		}
		return NULL;
        }
        if (index > dataptrlen) {
		excval = Py_BuildValue("(is)", 0, "index is greater than the string length");
		if (excval != NULL) {
			PyErr_SetObject(PyExc_ValueError, excval);
			Py_DECREF(excval);
		}
		return NULL;
        }
        dataptr = dataptr + index;
        dataptrlen = dataptrlen - index;
    } else if (PyBuffer_Check(dataobj)) {
        /* TODO accept buffer objects */
	    excval = Py_BuildValue("(is)", 0, "Buffer objects are not yet supported");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_TypeError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    } else {
	    excval = Py_BuildValue("(is)", 0, "parameter must be a python String object");
	    if (excval != NULL) {
		    PyErr_SetObject(PyExc_TypeError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    /*printf("dataptr = %p, dataptrlen = %d\n", dataptr, dataptrlen);*/
    /*printf("*dataptr = %s\n", dataptr);*/

    colonptr = strchr(dataptr, ':');
    if (!colonptr || (colonptr > dataptr + dataptrlen)) {
	    excval = Py_BuildValue("(is)", 0, "bad string length");
	    if (excval != NULL) {
		    PyErr_SetObject(MencodeError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }

    /* we don't use atoi() because it doesn't check for bad characters.  (does strtol?) */
    strlength = 0;
    digitptr = dataptr;
    while (digitptr < colonptr) {
        char digit = *digitptr;
        if ((digit < '0') || (digit > '9')) {
		excval = Py_BuildValue("(is)", 0, "length contained non-digit character");
		if (excval != NULL) {
			PyErr_SetObject(MencodeError, excval);
			Py_DECREF(excval);
		}
		return NULL;
        }
        strlength = (10*strlength) + (digit - '0');
        digitptr++;
    }

    if ((strlength != 0) && (*dataptr == '0')) {
	    excval = Py_BuildValue("(is)", 0, "positive string length must not begin with `0'");
	    if (excval != NULL) {
		    PyErr_SetObject(MencodeError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    dataend = colonptr + 1 + strlength - dataptr;
    if (dataend > dataptrlen) {
	    excval = Py_BuildValue("(is)", 0, "unexpected end of string");
	    if (excval != NULL) {
		    PyErr_SetObject(MencodeError, excval);
		    Py_DECREF(excval);
	    }
	    return NULL;
    }
    /* TODO return a buffer object instead of a string if strlength is over a determined threshold (40 chars or so?) */
    return Py_BuildValue("s#i", colonptr+1, strlength, dataend + index);
}

static PyMethodDef _c_mencode_helper_methods[] = {
    {"_c_decode_raw_string",  (PyCFunction)decode_raw_string,     METH_VARARGS},
    {"_c_encode_string",  (PyCFunction)encode_string,     METH_VARARGS},
    {"_c_encode_dict",  (PyCFunction)encode_dict,     METH_VARARGS},
    {"_c_encode_io",  (PyCFunction)encode_io,     METH_VARARGS},
    {NULL,      NULL}       /* sentinel */
};


DL_EXPORT(void) init_c_mencode_help(void)
{
    PyObject* m;
    PyObject* d;

    m = Py_InitModule("_c_mencode_help", _c_mencode_helper_methods);
    d = PyModule_GetDict(m);

    /* add our base exception class */
    MencodeError = PyErr_NewException("mencode._c_MencodeError", PyExc_StandardError, NULL);
    PyDict_SetItemString(d, "_c_MencodeError", MencodeError);

    encoder_dict = PyDict_New();
    PyDict_SetItemString(d, "_c_encoder_dict", encoder_dict);

    colon_tup_const = Py_BuildValue("(s)", ":");
    close_paren_tup_const = Py_BuildValue("(s)", ")");
    str_tup_const = Py_BuildValue("(s)", "(6:string");
    dict_tup_const = Py_BuildValue("(s)", "(4:dict");

    /* Check for errors */
    if (PyErr_Occurred()) {
        PyErr_Print();
        Py_FatalError("can't initialize module _c_mencode_help");
    }

}


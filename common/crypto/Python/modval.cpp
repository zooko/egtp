#include "integer.h"
#include "wrappedrsa.h"
#include "randsource_methods.h"
#include "filters.h"

//extern "C"
//{
#include "Python.h"
//}

USING_NAMESPACE(CryptoPP)

#define xdelete(p) delete (p); p = NULL
#define xdeletear(p) delete[] (p); p = NULL

PyObject *ModValError;

class MemoryException : public std::exception
{
public:
	explicit MemoryException() {}
	virtual ~MemoryException() throw() {}
};

typedef struct
{
	PyObject_HEAD
	WrappedRSAFunction *func;
	Integer *val;
} modular_value;

static PyObject *exposed_modular_value_verify_key_validity(modular_value *self, PyObject *args);

static char *modular_value_verify_key_validity(const byte *n, int keybytes);

static PyObject *exposed_modular_value_verify_key_and_value_validity(modular_value *self, PyObject *args);

static char *modular_value_verify_key_and_value_validity(const byte *n, int keybytes, const byte *val, int valbytes);

static void delete_modular_value(modular_value *self);

static int modular_value_get_exponent(const modular_value *self);

static PyObject *exposed_modular_value_encrypt(modular_value *self, PyObject *args);

static PyObject *exposed_modular_value_decrypt(modular_value *self, PyObject *args);

static void modular_value_encrypt(modular_value *self);

static void modular_value_decrypt(modular_value *self);

static PyObject *exposed_modular_value_divide(modular_value *self, PyObject *args);

static void modular_value_divide(modular_value *self, const modular_value *other);

static PyObject *exposed_modular_value_multiply(modular_value *self, PyObject *args);

static void modular_value_multiply(modular_value *self, const modular_value *other);

static PyObject *exposed_modular_value_get_private_key_encoding(modular_value *self, PyObject *args);

static PyObject *exposed_modular_value_get_modulus(modular_value *self, PyObject *args);

static PyObject *exposed_modular_value_get_exponent(modular_value *self, PyObject *args);

static PyObject *exposed_modular_value_get_value(modular_value *self, PyObject *args);

static PyObject *modular_value_getattr(modular_value *self, char* name);

static int modular_value_byte_count(const modular_value *self);

static void modular_value_store_modulus(const modular_value *self, byte *target);

static void modular_value_store_value(const modular_value *self, byte *target);

static PyObject *exposed_modular_value_set_value(modular_value *self, PyObject *args);

static PyObject *exposed_modular_value_set_value_string(modular_value *self, PyObject *args);

static void modular_value_set_value(modular_value *self, const modular_value *other);

statichere PyTypeObject Modular_type = {
        PyObject_HEAD_INIT(&PyType_Type)
        0,                        /*ob_size*/
        "ModularValue",                  /*tp_name*/
        sizeof(modular_value),        /*tp_size*/
        0,                        /*tp_itemsize*/
        /* methods */
        (destructor)delete_modular_value,  /*tp_dealloc*/
        0,                        /*tp_print*/
        (getattrfunc)modular_value_getattr, /*tp_getattr*/
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

static PyObject *exposed_modular_value_verify_key_and_value_validity(modular_value *self, PyObject *args);

static PyMethodDef modular_value_methods[] = {
  {"get_modulus", (PyCFunction)exposed_modular_value_get_modulus, METH_VARARGS, 
   "Returns the encoded value of the modulus as a string."
  }, 
  {"get_value", (PyCFunction)exposed_modular_value_get_value, METH_VARARGS, 
   "Returns the encoded currently stored value as a string."
  }, 
  {"get_private_key_encoding", (PyCFunction)exposed_modular_value_get_private_key_encoding, METH_VARARGS, 
   "Returns an encoded version for persistence."
  }, 
  {"get_exponent", (PyCFunction)exposed_modular_value_get_exponent, METH_VARARGS, 
   "Returns the exponent for encryption as an int."
  }, 
  {"encrypt", (PyCFunction)exposed_modular_value_encrypt, METH_VARARGS, 
   "Encrypts the currently stored value by bringing it to the\n"
   "specified exponent modulo the modulus."
  }, 
  {"decrypt", (PyCFunction)exposed_modular_value_decrypt, METH_VARARGS, 
   "Decrypts the currently stored value.\n"
   "Raises an exception if the private key is unavailable."
  }, 
  {"undo_signature", (PyCFunction)exposed_modular_value_encrypt, METH_VARARGS, 
   "The same as encrypt(), due to properties of the RSA algorithm."
  }, 
  {"sign", (PyCFunction)exposed_modular_value_decrypt, METH_VARARGS, 
   "The same as decrypt(), due to properties of the RSA algorithm."
  }, 
  {"set_value", (PyCFunction)exposed_modular_value_set_value, METH_VARARGS, 
   "Sets the currently stored value to be the same as what's stored in"
   "another modval.\n"
   "Takes a single parameter which is a modval. Does not take an integer\n"
   "or string since it's a good idea to always check that you're performing\n"
   "an operation on a compatible value."
  }, 
  {"set_value_string", (PyCFunction)exposed_modular_value_set_value_string, METH_VARARGS, 
   "Sets the currently stored value to be the same as what's stored in"
   "a string.\n"
   "Takes a single parameter which is an encoded value.\n"
   "It's usually a good idea to use set_value instead because that's safer."
  }, 
  {"multiply", (PyCFunction)exposed_modular_value_multiply, METH_VARARGS, 
   "Multiplies the stored value by the one stored in another modval\n"
   "modulo the modulus.\n"
   "Takes a single parameter which is a modval. Does not take an integer\n"
   "or string since it's a good idea to always check that you're performing\n"
   "an operation on a compatible value."
  }, 
  {"divide", (PyCFunction)exposed_modular_value_divide, METH_VARARGS, 
   "Multiplies the stored value by the multiplicative inverse of the one\n"
   "stored in another modval modulo the modulus.\n"
   "Takes a single parameter which is a modval. Does not take an integer\n"
   "or string since it's a good idea to always check that you're performing\n"
   "an operation on a compatible value."
  }, 
  {NULL, NULL}	/* sentinel */
};

static PyObject *exposed_modular_value_get_exponent(modular_value *self, PyObject *args)
{
	PyObject *result = NULL;
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		result = Py_BuildValue("i", modular_value_get_exponent(self));
		if(result == NULL)
		{
			throw MemoryException();
		}
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_encrypt(modular_value *self, PyObject *args)
{
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		modular_value_encrypt(self);
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_decrypt(modular_value *self, PyObject *args)
{
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		modular_value_decrypt(self);
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_get_private_key_encoding(modular_value *self, PyObject *args)
{
	PyObject *result = NULL;
        int len;
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
                std::string str = self->func->PrivateKeyEncoding(&len);
		result = PyString_FromStringAndSize(str.data(), str.length());
		if(!result)
		{
			throw MemoryException();
		}
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_get_modulus(modular_value *self, PyObject *args)
{
	byte *bytes = NULL;
	PyObject *result = NULL;
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		int size = modular_value_byte_count(self);
		bytes = new byte[size];
		modular_value_store_modulus(self, bytes);
		result = PyString_FromStringAndSize((char *)bytes, size);
		if(!result)
		{
			throw MemoryException();
		}
		xdeletear(bytes);
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
	  xdeletear(bytes);
	  PyMem_DEL(result);
	  PyErr_SetString(ModValError, e.what());
	  return NULL;
	}
	catch(MemoryException &e)
	{
	  xdeletear(bytes);
	  PyMem_DEL(result);
	  PyErr_SetString(PyExc_MemoryError, "out of memory");
	  return NULL;
	}
}

static PyObject *exposed_modular_value_multiply(modular_value *self, PyObject *args)
{
	try
	{
		modular_value *other;
		if(!PyArg_ParseTuple(args, "O!", &Modular_type, &other))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		modular_value_multiply(self, other);
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_divide(modular_value *self, PyObject *args)
{
	try
	{
		modular_value *other;
		if(!PyArg_ParseTuple(args, "O!", &Modular_type, &other))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		modular_value_divide(self, other);
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_set_value(modular_value *self, PyObject *args)
{
	try
	{
		modular_value *other;
		if(!PyArg_ParseTuple(args, "O!", &Modular_type, &other))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		modular_value_set_value(self, other);
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_set_value_string(modular_value *self, PyObject *args)
{
	try
	{
	    	byte *value;
		int valuelength;
		if(!PyArg_ParseTuple(args, "s#", &value, &valuelength))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		Integer newval = Integer(value, valuelength);
		if(newval >= self->func->GetModulus())
		{
		    	throw Exception("new value must be less than modulus");
		}
    		// assignment is overridden
	    	*self->val = newval;
		Py_INCREF(Py_None);
		return Py_None;
	}
	catch(CryptoPP::Exception &e)
	{
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_modular_value_get_value(modular_value *self, PyObject *args)
{
	byte *bytes = NULL;
	PyObject *result = NULL;
	try
	{
		if(!PyArg_ParseTuple(args, ""))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		int size = modular_value_byte_count(self);
		bytes = new byte[size];
		modular_value_store_value(self, bytes);
		result = PyString_FromStringAndSize((char *)bytes, size);
		if(!result)
		{
			throw MemoryException();
		}
		xdeletear(bytes);
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
	  xdeletear(bytes);
	  PyMem_DEL(result);
	  PyErr_SetString(ModValError, e.what());
	  return NULL;
	}
	catch(MemoryException &e)
	{
	  xdeletear(bytes);
	  PyMem_DEL(result);
	  PyErr_SetString(PyExc_MemoryError, "out of memory");
	  return NULL;
	}
}

static PyObject *modular_value_getattr(modular_value *self, char* name)
{
	return Py_FindMethod(modular_value_methods, (PyObject *)self, name);
}

static modular_value *new_modular_value_with_value(const byte *n, int keybytes, const byte *val, int valbytes, int e)
{
	modular_value *self = NULL;
	if(keybytes < 2)
	{
	    	throw Exception("key must be at least two bytes long");
	}
	if((e & 0x1) == 0)
	{
	    	throw Exception("encryption exponent must be odd");
	}
	if(e < 3)
	{
	    	throw Exception("encryption exponent must be at least 3");
    	}	
	if(valbytes > keybytes)
	{
		throw Exception("stored value can't be greater than modulus");
	}
	if(!(self = PyObject_NEW(modular_value, &Modular_type)))
	{
		throw MemoryException();
	}
	// to make deletion still work if there's an exception in construction
	// XXX not necessary -- it is okay to delete(NULL) in C++.  --Zooko 2001-11-18
	self->val = NULL;
	self->func = NULL;
	self->val = new Integer(val, (unsigned int)valbytes);
	self->func = new WrappedRSAFunction(Integer(n, (unsigned int)keybytes), Integer(e));
	if(!(n[0] & ((byte)0x80)))
	{
		throw Exception("key didn't start with a 1 bit");
	}
	if((keybytes == valbytes) && (*(self->val) >= self->func->GetModulus()))
	{
		throw Exception("stored value can't be greater than modulus");
	}
	return self;
}

static modular_value *new_modular_value_serialized(byte *bytes, int numbytes)
{
	modular_value *self = NULL;
	if(!(self = PyObject_NEW(modular_value, &Modular_type)))
	{
		throw MemoryException();
	}
	// to make deletion still work if there's an exception in construction
	self->val = NULL;
	self->func = NULL;
        StringStore bt(bytes, numbytes);
	self->func = new WrappedRSAFunction(bt);
	self->val = new Integer(NULL, 0, CryptoPP::Integer::UNSIGNED);
	return self;
}

static modular_value *new_modular_value_random(int keybytes, int e)
{
    	if(keybytes < 2)
	{
	    	throw Exception("key must be at least two bytes long");
    	}
	if((e & 0x1) == 0)
	{
	    	throw Exception("encryption exponent must be odd");
	}
	if(e < 3)
	{
	    	throw Exception("encryption exponent must be at least 3");
    	}	
	modular_value *self = NULL;
	if(!(self = PyObject_NEW(modular_value, &Modular_type)))
	{
		throw MemoryException();
	}
	// to make deletion still work if there's an exception in construction
	// XXX not necessary -- it is okay to delete(NULL) in C++.  --Zooko 2001-11-18
	self->val = NULL;
	self->func = NULL;
	self->func = new WrappedRSAFunction(keybytes * 8, Integer(e));
	self->val = new Integer(NULL, 0, CryptoPP::Integer::UNSIGNED);
	return self;
}

static void delete_modular_value(modular_value *self)
{
  if(self == NULL) {
    return;
  }
  xdelete(self->val);
  xdelete(self->func);
  PyMem_DEL(self);
}

static PyObject *exposed_modular_value_verify_key_validity(modular_value *self, PyObject *args)
{
	PyObject *result = NULL;
	try
	{
		byte *n;
		int keybytes;
		if(!PyArg_ParseTuple(args, "s#", &n, &keybytes))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		char *rchars = modular_value_verify_key_validity(n, keybytes);
		if(rchars == NULL)
		{
			Py_INCREF(Py_None);
			return Py_None;
		}		
		result = Py_BuildValue("s", rchars);
		if(result == NULL)
		{
			throw MemoryException();
		}
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static char *modular_value_verify_key_validity(const byte *n, int keybytes)
{
	if(keybytes < 2)
	{
		return "key must be at least two bytes long";
	}	
	if(!(n[0] & ((byte)0x80)))
	{
		return "first bit of modulus must be 1";
	}
	return NULL;
}

static PyObject *exposed_modular_value_verify_key_and_value_validity(modular_value *self, PyObject *args)
{
	PyObject *result = NULL;
	try
	{
		byte *n;
		int keybytes;
		byte *val;
		int valbytes;
		if(!PyArg_ParseTuple(args, "s#s#", &n, &keybytes, &val, &valbytes))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		char *rchars = modular_value_verify_key_and_value_validity(n, keybytes, val, valbytes);
		if(rchars == NULL)
		{
			Py_INCREF(Py_None);
			return Py_None;
		}		
		result = Py_BuildValue("s", rchars);
		if(result == NULL)
		{
			throw MemoryException();
		}
		return result;
	}
	catch(CryptoPP::Exception &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		PyMem_DEL(result);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static char *modular_value_verify_key_and_value_validity(const byte *n, int keybytes, const byte *val, int valbytes)
{
	if(keybytes < 2)
	{
		return "key must be at least two bytes long";
	}	
	if(!(n[0] & ((byte)0x80)))
	{
		return "first bit of modulus must be 1";
	}
	if(valbytes > keybytes)
	{
		return "modulus must be greater than value";
	}
	if(valbytes == keybytes && (Integer(n, (unsigned int)keybytes) <= Integer(val, (unsigned int)valbytes)))
	{
		return "modulus must be greater than value";
	}
	return NULL;
}

static void modular_value_encrypt(modular_value *self)
{
	// assignment is overridden
	*self->val = self->func->ApplyFunction(*self->val);
}

static void modular_value_decrypt(modular_value *self)
{
	// assignment is overridden
	*self->val = self->func->CalculateInverse(*self->val);
}

static void modular_value_multiply(modular_value *self, const modular_value *other)
{
	if(!self->func->Equals(*other->func))
	{
		throw Exception("Can only multiply values in the same modulus and exponent");
	}
	// assignment is overridden
	*self->val = self->func->Multiply(*self->val, *other->val);
}

static void modular_value_divide(modular_value *self, const modular_value *other)
{
	if(!self->func->Equals(*other->func))
	{
		throw Exception("Can only divide values in the same modulus and exponent");
	}
	*self->val = self->func->Divide(*self->val, *other->val);
}

static int modular_value_get_exponent(const modular_value *self)
{
	return (int)self->func->GetExponent().ConvertToLong();
}

static int modular_value_byte_count(const modular_value *self)
{
	return self->func->GetModulus().ByteCount();
}

static void modular_value_store_modulus(const modular_value *self, byte *target)
{
	Integer n = self->func->GetModulus();
	n.Encode(target, n.ByteCount());
}

static void modular_value_store_value(const modular_value *self, byte *target)
{
	Integer n = self->func->GetModulus();
	self->val->Encode(target, self->func->GetModulus().ByteCount());
}

static void modular_value_set_value(modular_value *self, const modular_value *other)
{
	if(!self->func->Equals(*other->func))
	{
		throw Exception("Can't assign value from a group with a different modulus or exponent");
	}
	// assignment is overridden
	*self->val = *other->val;
}

static PyObject *exposed_new_modval(PyObject *self, PyObject *args)
{
	modular_value *newself = NULL;
	try
	{
		byte *n;
		int keybytes;
		byte *val = NULL;
		int valbytes = 0;
		int e;
		if(!PyArg_ParseTuple(args, "s#i|s#", &n, &keybytes, &e, &val, &valbytes))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		newself = new_modular_value_with_value(n, keybytes, val, valbytes, e);
		return (PyObject *)newself;
	}
	catch(CryptoPP::Exception &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

static PyObject *exposed_new_random_modval(PyObject *self, PyObject *args)
{
	modular_value *newself = NULL;
	try
	{
		int keybytes;
		int e;
		if(!PyArg_ParseTuple(args, "ii", &keybytes, &e))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		newself = new_modular_value_random(keybytes, e);
		return (PyObject *)newself;
	}
	catch(CryptoPP::Exception &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
        catch(NotEnoughEntropyException &e)
        {
		delete_modular_value(newself);
		PyErr_SetString(PyExc_RuntimeError, "not enough entropy");
		return NULL;
        }
}

static PyObject *exposed_new_serialized_modval(PyObject *self, PyObject *args)
{
	modular_value *newself = NULL;
	try
	{
        	byte *encoded;
		int numencodedbytes;
		if(!PyArg_ParseTuple(args, "s#", &encoded, &numencodedbytes))
		{
		        PyErr_SetString(PyExc_ValueError, "incorrect parameter types");
		        return NULL;
		}
		newself = new_modular_value_serialized(encoded, numencodedbytes);
		return (PyObject *)newself;
	}
	catch(CryptoPP::Exception &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(ModValError, e.what());
		return NULL;
	}
	catch(MemoryException &e)
	{
		delete_modular_value(newself);
		PyErr_SetString(PyExc_MemoryError, "out of memory");
		return NULL;
	}
}

PyMethodDef modval_module_functions[] = {
  {"verify_key_and_value", (PyCFunction)exposed_modular_value_verify_key_and_value_validity, METH_VARARGS, 
   "Returns None if the key and value passed in are valid and compatible, \n"
   "otherwise returns a string explaining why they're not.\n"
   "Accepts two strings - (key, value)."
  }, 
  {"verify_key", (PyCFunction)exposed_modular_value_verify_key_validity, METH_VARARGS, 
   "Returns None if the key passed in is valid, otherwise returns a string\n"
   "explaining why it's not.\n"
   "Accepts a string."
  }, 
  {"new", (PyCFunction)exposed_new_modval, METH_VARARGS, 
   "Creates a new modular value with a specified modulus and exponent and\n"
   "optionally an initial value. Resulting modval cannot decrypt or sign.\n"
   "Accepts a string (the encoded modulus), an int which is the exponent for\n"
   "encryption, and optionally an encoded initial value. If an initial value\n"
   "isn't given it will be set to zero. It is safe to specify any value\n"
   "of shorter length than the modulus. Values of exactly the same length which\n"
   "are generated at random (rather than as a result of get_value()) will\n"
   "sometimes raise an exception. It is highly inadvisable to try to manually\n"
   "generate moduli rather than getting them from the get_modulus() method of\n"
   "an object which was created using new_random()."
  }, 
  {"new_random", (PyCFunction)exposed_new_random_modval, METH_VARARGS, 
   "Creates a new modular value with a randomly generated modulus containing\n"
   "private key information and with a value initialized to zero.\n"
   "Accepts int which is the number of bytes (not bits) in the modulus, and an int\n"
   "which is the encryption exponent."
  }, 
  {"new_serialized", (PyCFunction)exposed_new_serialized_modval, METH_VARARGS, 
   "Creates a new modular value from the results of a prior \n"
   "get_private_key_encoding()\n"
   "Throws a ModValError if the string is formatted wrong\n"
  }, 
  {NULL, NULL}	/* Sentinel */
};

char* module_doc =
"Represents an integer operating in the context of a specific RSA modulus and\n"
"encryption exponent.\n"
"Contains an unchangeable modulus and exponent (which are compared to all other\n"
"modvals operated on for sanity) plus a mutable integer which the various methods\n"
"operate on.\n"
"This class handles encoding and decoding in addition to arithmetic operations, so\n"
"all the exposed methods use strings. The only non-obvious consequence is that when\n"
"randomly generating a value to store in a modval you have to make it be at least one\n"
"byte shorter than the modulus, even though the result of performing operations on it\n"
"may be the same length as the modulus.\n"
"\n"
"See individual method documentation for detailed information on how to use them.\n"
"\n"
"The static methods are - \n"
"new - constructor\n"
"new_random - constructs a new randomly generated modval\n"
"verify_key - for sanity checking data sent in over the wire\n"
"verify_key_and_value - for sanity checking data sent in over the wire\n"
"\n"
"The instance methods are - \n"
"get_modulus - accessor\n"
"get_value - accessor\n"
"get_exponent - accessor\n"
"encrypt - encrypts the stored value\n"
"decrypt - decrypts the stored value\n"
"sign - same as decrypt\n"
"undo_signature - same as encrypt\n"
"set_value - sets the stored value to what's in another modval\n"
"set_value_string - sets the stored value to what's in a string\n"
"multiply - multiplies the stored value by another one\n"
"divide - divides the stored value by another one";

/* Initialize this module. */

extern "C"
{
DL_EXPORT(void)
initmodval()
{
        PyObject *m, *d;
	m = Py_InitModule3("modval", modval_module_functions, module_doc);
        d = PyModule_GetDict(m);
        ModValError = PyErr_NewException("modval.Error", NULL, NULL);
        PyDict_SetItemString(d, "Error", ModValError);
}
}


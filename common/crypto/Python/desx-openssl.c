/**************************************************************************
Return-Path: <mojonation-devel-admin@lists.sourceforge.net>
Delivered-To: greg@mad-scientist.com
From: hal@finney.org
Message-Id: <200010110533.WAA05674@finney.org>
To: mojonation-devel@lists.sourceforge.net
Subject: Re: [Mojonation-devel] Crypto++ vs OpenSSL
Sender: mojonation-devel-admin@lists.sourceforge.net
Errors-To: mojonation-devel-admin@lists.sourceforge.net
Reply-To: mojonation-devel@lists.sourceforge.net
Date: Tue, 10 Oct 2000 22:33:55 -0700

Well, here is the interface module for using OpenSSL's DES support.
It sounds like it won't be worthwhile to switch until all of the crypto
is converted over, and unfortunately I don't have time to take on that
big a task.  Perhaps this will be of use at some point in the future.

I did fix it to work properly with short (1 block) messages, altering
the IV in that case, and it seems to work OK.

Hal
**************************************************************************/
/*
 * Changing the IV out from under python is Wrong --- python strings
 * are immutable.  Better to use CFB mode, or return both ciphertext
 * and (possibly modified) IV.  In the meantime, I'll disable this
 * "feature".  - Andrew Archibald
 */

/*
 * NOTE: we don't actually use tripledes (3des), we use DES-X
 * (X-DES-X) mode, our code misnames things. -g
 */

/*
 * This file uses `free()' on objects that were allocated in tripledescbc.cpp with `new'.
 * They are destructorless, so this probably works on most compilers, but they should be
 * changed to use `delete[]' instead.  --Zooko 2001-08-28
 */

=========================================================

/* Interface to OpenSSL 3DES code, using CBC with ciphertext stealing */
#include "Python.h"

/* From OpenSSL */
#include "openssl/des.h"

/* Block size of DES */
#define BS	8

PyObject *TripleDESCBCError;

typedef struct
{
	PyObject_HEAD
	u_char *key;
} tripledescbc;

static PyObject *tripledescbc_new(tripledescbc *self, PyObject *args);

static void tripledescbc_delete(tripledescbc *self);

static PyObject *tripledescbc_encrypt(tripledescbc *self, PyObject *args);

static PyObject *tripledescbc_decrypt(tripledescbc *self, PyObject *args);

static PyObject *tripledescbc_getattr(tripledescbc *self, char* name);

statichere PyTypeObject tripledescbc_type = {
        PyObject_HEAD_INIT(&PyType_Type)
        0,                        /*ob_size*/
        "DES-XEX3CBC",                  /*tp_name*/
        sizeof(tripledescbc),        /*tp_size*/
        0,                        /*tp_itemsize*/
        /* methods */
        (destructor)tripledescbc_delete,  /*tp_dealloc*/
        0,                        /*tp_print*/
        (getattrfunc)tripledescbc_getattr, /*tp_getattr*/
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

static PyMethodDef tripledescbc_methods[] = {
  {"encrypt", (PyCFunction)tripledescbc_encrypt, METH_VARARGS, 
   "Returns an encrypted string.\n"
   "Accepts an IV string of length 8 and a plaintext string.\n"
   "Encrypts in CBC mode with ciphertext stealing.\n"
   "Always returns a ciphertext of the exact same length as the plaintext."
  }, 
  {"decrypt", (PyCFunction)tripledescbc_decrypt, METH_VARARGS, 
   "Returns a decrypted string.\n"
   "Accepts an IV string of length 8 and a ciphertext string.\n"
   "Decrypts in CBC mode with ciphertext stealing.\n"
   "Always returns a plaintext of the exact same length as the ciphertext."
  }, 
  {NULL, NULL}	/* sentinel */
};

static PyObject *tripledescbc_getattr(tripledescbc *self, char* name)
{
	return Py_FindMethod(tripledescbc_methods, (PyObject *)self, name);
}

static void tripledescbc_delete(tripledescbc *self) {
	if(self != NULL) {
		free( self->key );
		PyMem_DEL(self);
	}
}

static PyObject *tripledescbc_new(tripledescbc *self, PyObject *args) {
	tripledescbc *newself = NULL;
	u_char *key;
	u_char *keycopy;
	int keylength;
	if(!PyArg_ParseTuple(args, "s#", &key, &keylength)) {
		PyErr_SetString(PyExc_ValueError, 
						"wrong type of parameters passed in from Python");
		return NULL;
	}
	if(keylength != 24) {
		PyErr_SetString(PyExc_ValueError, 
						"triple DES key length must be 24");
		return NULL;
	}
	if(!(newself = PyObject_NEW(tripledescbc, &tripledescbc_type))) {
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}
	keycopy = (u_char *)malloc(24);
	if(keycopy == NULL)
	{
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}
	memcpy(keycopy, key, 24);
	newself->key = keycopy;
	return (PyObject *)newself;
}


static PyObject *tripledescbc_encrypt(tripledescbc *self, PyObject *args) {
	PyObject *result = NULL;
	u_char *ciphertext = NULL;
	u_char *cipherlastblock;
	u_char *iv;
	u_char ivcopy[BS];
	unsigned int ivlength;
	u_char *text;
	u_char tbuf[BS];
	unsigned int lastblocklength;
	unsigned int textlength;
	des_key_schedule ks;

	if(!PyArg_ParseTuple(args, "s#s#", &iv, &ivlength, &text, &textlength)) {
		PyErr_SetString(PyExc_ValueError, 
						"wrong type of parameters passed in from Python");
		return NULL;
	}
	if(ivlength != BS) {
		PyErr_SetString(PyExc_ValueError, "IV length must equal block size");
		return NULL;
	}
	if(textlength < BS) {
		PyErr_SetString(PyExc_ValueError, "Ciphertext is shorter than block size");
		return NULL;
	}
printf ("iv: %02x%02x%02x%02x%02x%02x%02x%02x\n", iv[0], iv[1], iv[2], iv[3], iv[4], iv[5], iv[6], iv[7]);
	memcpy( ivcopy, iv, BS );

	lastblocklength = ((textlength-1) % BS) + 1;	/* in range 1-BS */
	ciphertext = (u_char *)malloc(textlength + BS - lastblocklength);	/* mul of BS */
	if(ciphertext == NULL)
	{
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}

	des_key_sched((const_des_cblock *)(self->key+BS), ks);
	/* Note that this implicitly pads with zeros */
	/* Also note that it overwrites the iv array */
	des_xcbc_encrypt( text, ciphertext, textlength, ks, (des_cblock *)ivcopy,
					  (des_cblock *)self->key, (des_cblock *)(self->key+2*BS),
					  1 );
		
	/* Swap final blocks for CTS mode */
	if(textlength <= BS) {
		/* Special handling if only one block - swap ciphertext & IV */
		memcpy( tbuf, ciphertext, BS );
		memcpy( ciphertext, iv, textlength );
		/* Note that this changes the IV value of the caller */
		memcpy( iv, tbuf, BS );
	} else {
		cipherlastblock = ciphertext + textlength - lastblocklength;
		memcpy( tbuf, cipherlastblock, BS );
		memcpy( cipherlastblock, cipherlastblock - BS, lastblocklength );
		memcpy( cipherlastblock - BS, tbuf, BS );
	}

	/* Implicitly truncate new last block for CTS mode */
	result = Py_BuildValue("s#", ciphertext, textlength);
	if(result == NULL)
	{
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}
	free( ciphertext );
	return result;
}

static PyObject *tripledescbc_decrypt(tripledescbc *self, PyObject *args) {
	PyObject *result = NULL;
	u_char *plaintext = NULL;
	u_char *plainlastblock;
	u_char *iv;
	u_char ivcopy[BS];
	unsigned int ivlength;
	u_char *text;
	u_char *textlastblock;
	unsigned int textlength;
	unsigned int lastblocklength;
	des_key_schedule ks;
	u_char tbuf[BS];

	if(!PyArg_ParseTuple(args, "s#s#", &iv, &ivlength, &text, &textlength)) {
		PyErr_SetString(PyExc_ValueError, 
						"wrong type of parameters passed in from Python");
		return NULL;
	}
	/* Ciphertext stealing requires at least two blocks */
	if(ivlength != BS) {
		PyErr_SetString(PyExc_ValueError, "IV length must equal block size");
		return NULL;
	}
	if(textlength < BS) { 
 	      /* Not strictly necessary: this routine works fine with
		 short ciphertexts, unlike encrypt() above.  But until
		 that code is fixed, there's no way to encrypt a short
		 ciphertext so that it can be decrypted here */
		PyErr_SetString(PyExc_ValueError, "Ciphertext is shorter than block size");
		return NULL;
	}
printf ("iv: %02x%02x%02x%02x%02x%02x%02x%02x\n", iv[0], iv[1], iv[2], iv[3], iv[4], iv[5], iv[6], iv[7]);
	memcpy( ivcopy, iv, BS );

	lastblocklength = ((textlength-1) % BS) + 1;	/* in range 1-BS */
	plaintext = (u_char *)malloc(textlength + BS - lastblocklength);	/* mul of BS */
	if(plaintext == NULL)
	{
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}

	/* Pointers to final block, of length 1-BS bytes */
	plainlastblock = plaintext + textlength - lastblocklength;
	textlastblock = text + textlength - lastblocklength;

	des_key_sched((const_des_cblock *)(self->key+BS), ks);

	if(textlength <= BS) {
		/* Short messages require special treatment */
		/* Effectively interchange IV and zero-padded plaintext */
		memcpy( tbuf, text, textlength );
		memset( tbuf+textlength, 0, BS-textlength );
		des_xcbc_encrypt( ivcopy, plaintext, textlength, ks,
						  (des_cblock *)tbuf, (des_cblock *)self->key,
						  (des_cblock *)(self->key+2*BS), 0 );
	} else {
		/* decrypt all but last two blocks */
		/* Note that this implicitly pads with zeros */
		/* Also note that it overwrites the iv array */
		des_xcbc_encrypt( text, plaintext, textlength-lastblocklength-BS, ks,
						  (des_cblock *)iv, (des_cblock *)self->key,
						  (des_cblock *)(self->key+2*BS), 0 );

		/* Calculate last block, with padding */
		memcpy( tbuf, textlastblock, lastblocklength );
		memset( tbuf+lastblocklength, 0, BS-lastblocklength );
		memcpy( ivcopy, tbuf, BS );
		des_xcbc_encrypt( textlastblock-BS, plainlastblock, BS, ks,
						  (des_cblock *)ivcopy, (des_cblock *)self->key,
						  (des_cblock *)(self->key+2*BS), 0 );

		/* Calculate next to last block */
		memcpy( tbuf+lastblocklength, plainlastblock+lastblocklength,
				BS-lastblocklength );
		memcpy( ivcopy, textlastblock-2*BS, BS );
		des_xcbc_encrypt( tbuf, plainlastblock-BS, BS, ks,
						  (des_cblock *)ivcopy, (des_cblock *)self->key,
						  (des_cblock *)(self->key+2*BS), 0 );
	}

	/* Implicitly truncate last block for CTS mode */
	result = Py_BuildValue("s#", plaintext, textlength);
	if(result == NULL)
	{
		PyErr_SetString(PyExc_MemoryError, "couldn't allocate memory");
		return NULL;
	}
	free( plaintext );
	return result;
}

PyMethodDef tripledescbc_functions[] = {
  {"new", (PyCFunction)tripledescbc_new, METH_VARARGS, 
   "Constructs a new tripledescbc.\n"
   "Accepts a key of length 24."
  }, 
  {NULL, NULL}	/* Sentinel */
};

char* tripledescbc_doc =
"Does 3DES encryption and decyption in CBC mode with ciphertext stealing.\n"
"Always uses a key of length 24 and initialization vectors of length 8.\n"
"\n"
"Class methods are - \n"
"new(key) - constructor\n"
"\n"
"Instance methods are - \n"
"encrypt(iv, plaintext) - encrypt a string\n"
"decrypt(iv, ciphertext) - decrypt a string";

/* Initialize this module. */

DL_EXPORT(void)
inittripledescbc()
{
        PyObject *m, *d;
	m = Py_InitModule3("tripledescbc", tripledescbc_functions, tripledescbc_doc);
        d = PyModule_GetDict(m);
        TripleDESCBCError = PyErr_NewException("tripledescbc.Error", NULL, NULL);
        PyDict_SetItemString(d, "Error", TripleDESCBCError);
}


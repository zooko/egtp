#ifndef INCL_wrappedrsa_hh
#define INCL_wrappedrsa_hh

#include "rsa.h"
#include "modarith.h"
#include "integer.h"

USING_NAMESPACE(CryptoPP)

class WrappedRSAFunction
{
public:
	// destructor
	~WrappedRSAFunction();
	
	// Creates a function which only handles the public key operations
	WrappedRSAFunction(const Integer &n,const Integer &e);
	
	// Creates a random new function which handles both public and private key operations.
	// The exponent of the returned function is guaranteed to be exactly equal to the one 
	// passed in.
	WrappedRSAFunction(unsigned int keybits,const Integer &e);

	// for deserialization
	WrappedRSAFunction(BufferedTransformation& bt);

	// Returns n.
	const Integer& GetModulus() const;

	// Returns e.
	const Integer& GetExponent() const;

	// Returns x*y(mod n). Useful for blinded signatures.
	Integer Multiply(const Integer &x,const Integer &y) const;

	// Returns x/y(mod n). Useful for blinded signatures.
	Integer Divide(const Integer &numerator,const Integer &denominator) const;

	// Returns the encrypted form of x.
	Integer ApplyFunction(const Integer &x) const;
	
	// Returns the decrypted form of x.
	Integer CalculateInverse(const Integer &x);
	
	// returns n == other.n && e == other.e
	bool Equals(const WrappedRSAFunction &other) const;
	
        // returns an encoded version of the private key, if known
        // otherwise throws an Exception
        std::string PrivateKeyEncoding(int *len);
        
protected:
	RSAFunction *func;
	InvertibleRSAFunction *invertibleFunction;
};

#endif // #ifndef INCL_wrappedrsa_hh


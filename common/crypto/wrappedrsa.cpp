#include "rsa.h"
#include "integer.h"
#include "randsource_methods.h"
#include "wrappedrsa.h"
#include "cryptlib.h"
#include "filters.h"

WrappedRSAFunction::WrappedRSAFunction(const Integer &n,const Integer &e)
{
	func = new RSAFunction(n,e);
	invertibleFunction = NULL;
}

WrappedRSAFunction::WrappedRSAFunction(BufferedTransformation& bt)
{
	invertibleFunction = new InvertibleRSAFunction(bt);
        func = invertibleFunction;
}

WrappedRSAFunction::~WrappedRSAFunction()
{
	// func and invertibleFunction are the same thing, so only one needs to be deleted
	delete func;
}

WrappedRSAFunction::WrappedRSAFunction(unsigned int keybits,const Integer &e)
{
	// yeah, yeah, I know, but there's no way to forcibly set the exponent 
	// other than by trying till it works, so this bit of silliness is necessary.
	while(true)
	{
		RandsourceRandomNumberGenerator rand = RandsourceRandomNumberGenerator();
		invertibleFunction = new InvertibleRSAFunction(rand,keybits,e);
		if(invertibleFunction->GetExponent() == e)
		{
			break;
		}
		delete invertibleFunction;
	}
	func = invertibleFunction;
}

const Integer& WrappedRSAFunction::GetModulus() const
{
	return func->GetModulus();
}

const Integer& WrappedRSAFunction::GetExponent() const
{
	return func->GetExponent();
}

Integer WrappedRSAFunction::Multiply(const Integer &x,const Integer &y) const
{
	return x * y % GetModulus();
}

Integer WrappedRSAFunction::Divide(const Integer &numerator,const Integer &denominator) const
{
	Integer modulus = GetModulus();
	Integer inverse = denominator.InverseMod(modulus);
	if(inverse == Integer::Zero())
	{
		throw Exception("can't divide by a value with no inverse");
	}
	return numerator * inverse % modulus;
}

Integer WrappedRSAFunction::ApplyFunction(const Integer &x) const
{
	return func->ApplyFunction(x);
}

Integer WrappedRSAFunction::CalculateInverse(const Integer &x)
{
	if(invertibleFunction == NULL)
	{
		throw Exception("WrappedRSAFunction: Private key not available");
	}
	return invertibleFunction->CalculateInverse(x);
}

std::string WrappedRSAFunction::PrivateKeyEncoding(int *len)
{
	if(invertibleFunction == NULL)
        {
		throw Exception("WrappedRSAFunction: Private key not available");
        }
        std::string str;
        StringSink bt(str);
        invertibleFunction->DEREncode(bt);
        return str;
}

bool WrappedRSAFunction::Equals(const WrappedRSAFunction &other) const
{
	return GetModulus() == other.GetModulus() && GetExponent() == other.GetExponent();
}

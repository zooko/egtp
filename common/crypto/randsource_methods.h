#ifndef INCL_randsource_methods_hh
#define INCL_randsource_methods_hh

#include "cryptlib.h"

USING_NAMESPACE(CryptoPP)


class RandsourceRandomNumberGenerator : public RandomNumberGenerator {
public:
#ifdef CRYPTOPP_42
        byte GenerateByte();
        void GenerateBlock(byte *output,unsigned int size);
#else
#ifdef CRYPTOPP_41
        byte GenerateByte();
        void GenerateBlock(byte *output,unsigned int size);
#else
#ifdef CRYPTOPP_40
        byte GenerateByte();
        void GenerateBlock(byte *output,unsigned int size);
#else
        byte GetByte();
        void GetBlock(byte *output,unsigned int size);
#endif
#endif
#endif
};

class NotEnoughEntropyException : public std::exception {
public:
	explicit NotEnoughEntropyException() { }
	virtual ~NotEnoughEntropyException() throw() { }
};

extern "C"
{
extern void randsource_add(const unsigned char *data,unsigned int amount,unsigned int entropybits);

extern int randsource_get(unsigned char *data,unsigned int amount);
}

#endif // #ifndef INCL_randsource_methods_hh


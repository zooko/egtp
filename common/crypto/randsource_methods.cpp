#include "randsource_methods.h"

#include "sha.h"

USING_NAMESPACE(CryptoPP)

extern "C"
{
void randsource_add(const unsigned char *data,unsigned int amount,unsigned int entropybits);

int randsource_get(unsigned char *data,unsigned int amount);
}

void randsource_mix();


unsigned int randsource_output_pos = 666;

unsigned int randsource_pooled_bits = 0;

#ifdef WIN32
byte *randsource_state = new byte[20];
byte *randsource_output = new byte[20];
byte *randsource_scratch = new byte[20];
#else
byte randsource_state[20] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
byte randsource_output[20] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
byte randsource_scratch[20] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
#endif

SHA *randsource_pool = new SHA();


// The number of bits to collect before adding them into the random pool.  This
// chunking is important to prevent an attacker who knows the state of the random
// pool at time T from "following" the state through successive times by
// brute-forcing small additions to the pool.  (I.e., if 40 bits are added to the
// pool and then some new random bytes are retrieved from the pool, an attacker
// could try all 2^40 possible inputs to see which yields the given output.)
// Note that a particularly common case of the attacker knowing the state of the
// pool is when the pool is brand new and has a state of all zeroes.

static const unsigned int CHUNK_SIZE = 80;


#ifdef CRYPTOPP_42
byte RandsourceRandomNumberGenerator::GenerateByte() {
#else
#ifdef CRYPTOPP_41
byte RandsourceRandomNumberGenerator::GenerateByte() {
#else
#ifdef CRYPTOPP_40
byte RandsourceRandomNumberGenerator::GenerateByte() {
#else
byte RandsourceRandomNumberGenerator::GetByte() {
#endif
#endif
#endif
        byte r;
        if(!randsource_get(&r,1)) {
                throw NotEnoughEntropyException();
        } 
        return r;
}

#ifdef CRYPTOPP_42
void RandsourceRandomNumberGenerator::GenerateBlock(byte *output,unsigned int size) {
#else
#ifdef CRYPTOPP_41
void RandsourceRandomNumberGenerator::GenerateBlock(byte *output,unsigned int size) {
#else
#ifdef CRYPTOPP_40
void RandsourceRandomNumberGenerator::GenerateBlock(byte *output,unsigned int size) {
#else
void RandsourceRandomNumberGenerator::GetBlock(byte *output,unsigned int size) {
#endif
#endif
#endif
        if(!randsource_get(output,size)) {
                throw NotEnoughEntropyException();
        }
}                      


extern "C"
{
// intended to be used from C
void randsource_add(const unsigned char *data,unsigned int amount,unsigned int entropybits) {
	// add new data to the pool
        if (randsource_pool == NULL) {
            // this is here because OpenBSD doesn't appear to properly
            // initialize things declared as new FOO's in the global
            // scope on module import.  It's probably a C++ library
            // version / linkage issue.  yuck.
            randsource_pool = new SHA();
        }
	randsource_pool->Update(data,amount);
	randsource_pooled_bits += entropybits;
	// if enough entropy has been pooled add it to the main state
	if(randsource_pooled_bits >= CHUNK_SIZE) {
		randsource_pool->Final(randsource_scratch);
		// xor the main state with the hash of everything pooled
		for(int i = 0;i < 20;i++) {
			randsource_state[i] ^= randsource_scratch[i];
		}
		// reset the pool
		delete randsource_pool;
		randsource_pool = new SHA();
		randsource_pooled_bits = 0;
		// generate some new output
		randsource_mix();
	}
}

// intended to be used from C
int randsource_get(unsigned char *data,unsigned int amount) {
	if(randsource_output_pos == 666) {
		// can't return any random numbers until entropy has been collected
		return false;
	}
	for(unsigned int i = 0;i < amount;i++) {
		data[i] = randsource_output[randsource_output_pos++];
		// if the last block of output is exhausted, make a new one
		if(randsource_output_pos == 20) {
			randsource_mix();
		}
	}
	return true;
}
} /* extern "C" */

// computes some new output and garbles the main state
void randsource_mix() {
	// compute some new output by setting it to the 
	// hash of the state
	SHA *sh1 = new SHA();
	sh1->Update(randsource_state,20);
	sh1->Final(randsource_output);
	randsource_output_pos = 0;
	delete sh1;

	// garble the main state by setting it to the hash 
	// of itself with all bits flipped
	// that way it's impossible to compute the new state 
	// from the new output
	SHA *sh2 = new SHA();
	for(int i = 0;i < 20;i++) {
		randsource_state[i] ^= 0xFF;
	}
	sh2->Update(randsource_state,20);
	sh2->Final(randsource_state);
	delete sh2;
}

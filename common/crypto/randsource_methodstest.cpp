#include "randsource_methods.h"
#include <assert.h>
#include <stdio.h>

int main(int argc, char* argv[]) {
	byte buf[20] = { 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X', 'X' };
	
	randsource_add(buf, 20, 160);

	int ret = randsource_get(buf, 20);

	assert(ret == 1);

	printf("success: ret is 1 and buf is: ");

	int i;

	for (i = 0; i < 20; i++) {
		printf("%u", buf[i]);
	}

	printf("\n");
}


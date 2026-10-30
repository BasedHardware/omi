CC ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -I../src/lib/core
SD_CFLAGS ?= -std=c99 -Wall -Wextra -Werror -Istubs -I../src -I../src/lib/core -Wno-unused-parameter -Wno-unused-variable
STUB_HEADERS := $(wildcard stubs/*.h stubs/*/*.h stubs/*/*/*.h stubs/*/*/*/*.h)
CUSTODY_SRC := ../src/lib/core/custody.c ../src/lib/core/custody.h

test_custody: test_custody.c $(CUSTODY_SRC)
	$(CC) $(CFLAGS) -o $@ test_custody.c ../src/lib/core/custody.c

test_sd_card: test_sd_card.c ../src/sd_card.c $(CUSTODY_SRC) $(STUB_HEADERS)
	$(CC) $(SD_CFLAGS) -o $@ test_sd_card.c ../src/lib/core/custody.c

test_storage: test_storage.c ../src/lib/core/storage.c $(CUSTODY_SRC) $(STUB_HEADERS)
	$(CC) $(SD_CFLAGS) -o $@ test_storage.c ../src/lib/core/custody.c

run: test_custody test_sd_card test_storage
	./test_custody
	./test_sd_card
	./test_storage

clean:
	rm -f test_custody test_sd_card test_storage

.PHONY: run clean

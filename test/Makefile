# Host tests, moved here from the player's texttest/ with the code they
# test. texttest is the real src/gfx.c text path against shim.h's
# stand-in for ESP-IDF; the other three are header-only.
#
#   make -C test
#
# shim.c, shim.h and fake/ are copies of the player's: it keeps its own
# for its other tests.
#
# SPDX-License-Identifier: MIT

CC ?= cc

INC := -I. -Ifake -I../include -I../fonts/ark12 -I../fonts/arabixel
WARNCFLAGS := -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter \
              -D_GNU_SOURCE $(INC)
CFLAGS  := -std=c11 -g -O1 -Wall -Wextra -Wno-unused-parameter \
           -fsanitize=address,undefined -fno-sanitize-recover=all \
           -fno-omit-frame-pointer $(INC)
LDFLAGS := -fsanitize=address,undefined -lm

SRCS := main.c shim.c ../src/gfx.c ../fonts/ark12/ark12.c \
        ../fonts/arabixel/arabixel_tab.c ../fonts/arabixel/arabixel_shape.c

all: run run-bidi run-logcut run-bright

texttest: $(SRCS) shim.h ../include/gfx.h ../include/bidiline.h \
          ../fonts/ark12/ark12.h ../fonts/arabixel/arabixel.h
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(LDFLAGS)

run: texttest
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 ./texttest

bidilinetest: bidilinetest.c ../include/bidiline.h
	$(CC) $(WARNCFLAGS) -c bidilinetest.c -o /dev/null
	$(CC) $(CFLAGS) -o $@ bidilinetest.c $(LDFLAGS)

run-bidi: bidilinetest
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 ./bidilinetest

logcuttest: logcuttest.c ../include/logcut.h
	$(CC) $(WARNCFLAGS) -c logcuttest.c -o /dev/null
	$(CC) $(CFLAGS) -D_GNU_SOURCE -o $@ logcuttest.c $(LDFLAGS)

run-logcut: logcuttest
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 ./logcuttest

brightnesstest: brightnesstest.c ../include/brightness.h
	$(CC) $(WARNCFLAGS) -c brightnesstest.c -o /dev/null
	$(CC) $(CFLAGS) -o $@ brightnesstest.c $(LDFLAGS)

run-bright: brightnesstest
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 ./brightnesstest

clean:
	rm -f texttest bidilinetest logcuttest brightnesstest

.PHONY: all run run-bidi run-logcut run-bright clean

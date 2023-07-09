MODULES = hoordu

EXTENSION = hoordu
DATA = hoordu--1.0.sql
PGFILEDESC = "hoordu - text search configuration for hoordu"

REGRESS = hoordu

ifdef USE_PGXS
PG_CONFIG = pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
else
subdir = contrib/hoordu
top_builddir = ../..
include $(top_builddir)/src/Makefile.global
include $(top_srcdir)/contrib/contrib-global.mk
endif

CONTIKI_PROJECT = udp-client udp-server
all: $(CONTIKI_PROJECT)

CFLAGS += -DPROJECT_CONF_H=\"project-conf.h\"

PROJECT_SOURCEFILES += rpl-sarsa.c 

CONTIKI=../..
include $(CONTIKI)/Makefile.include


/*
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the Institute nor the names of its contributors
 *    may be used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE INSTITUTE AND CONTRIBUTORS ``AS IS'' AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE INSTITUTE OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 * OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 *
 * This file is part of the Contiki operating system.
 *
 */

#include "contiki.h"
#include "net/routing/routing.h"
#include "net/netstack.h"
#include "net/ipv6/simple-udp.h"

#ifdef FEDERATION
  #include <stdint.h>
  #include <inttypes.h>
  #include "energest.h"
#endif

#include "sys/log.h"
#define LOG_MODULE "App"
#define LOG_LEVEL LOG_LEVEL_INFO

#define WITH_SERVER_REPLY  1
#define UDP_CLIENT_PORT	8765
#define UDP_SERVER_PORT	5678

#ifdef FEDERATION

  #define FED_MAGIC 0xFA
  
  /* Federated learning payload structs — must match udp-client.c */
  typedef struct {
    uint8_t magic;
    uint32_t seq;
    int32_t  w_lq;
    int32_t  w_energy;
    char app_data[32];
  } __attribute__((packed)) udp_fed_payload_t;

  typedef struct {
    uint8_t magic;
    int32_t  agg_w_lq;
    int32_t  agg_w_energy;
    uint8_t  num_nodes;
  } __attribute__((packed)) udp_fed_reply_t;

  /* FL aggregation state: per-node snapshot average (most recent weights per sender) */
  #ifndef FL_MAX_NODES
  #define FL_MAX_NODES 10
  #endif

  typedef struct {
    uip_ipaddr_t  addr;
    int32_t       w_lq;
    int32_t       w_energy;
  } fl_node_entry_t;

  static fl_node_entry_t fl_nodes[FL_MAX_NODES];
  static uint8_t         fl_node_count = 0;
#endif

static struct simple_udp_connection udp_conn;

PROCESS(udp_server_process, "UDP server");
AUTOSTART_PROCESSES(&udp_server_process);
/*---------------------------------------------------------------------------*/
static void
udp_rx_callback(struct simple_udp_connection *c,
         const uip_ipaddr_t *sender_addr,
         uint16_t sender_port,
         const uip_ipaddr_t *receiver_addr,
         uint16_t receiver_port,
         const uint8_t *data,
         uint16_t datalen)
{
  #ifdef FEDERATION
    if(datalen == sizeof(udp_fed_payload_t) && ((const udp_fed_payload_t *)data)->magic == FED_MAGIC) {
      // Federation packet received
      const udp_fed_payload_t *pl = (const udp_fed_payload_t *)data;

      /* Find existing entry for this sender, or insert a new one */
      uint8_t i;
      for(i = 0; i < fl_node_count; i++) {
        if(uip_ipaddr_cmp(&fl_nodes[i].addr, sender_addr)) {
          break;
        }
      }
      if(i == fl_node_count && fl_node_count < FL_MAX_NODES) {
        uip_ipaddr_copy(&fl_nodes[i].addr, sender_addr);
        fl_node_count++;
      }
      if(i < fl_node_count) {
        fl_nodes[i].w_lq     = pl->w_lq;
        fl_nodes[i].w_energy = pl->w_energy;
      }

      /* Recompute snapshot average using only the most recent value from each node */
      int32_t sum_lq = 0, sum_energy = 0;
      for(i = 0; i < fl_node_count; i++) {
        sum_lq     += fl_nodes[i].w_lq;
        sum_energy += fl_nodes[i].w_energy;
      }
      int32_t avg_w_lq     = fl_node_count > 0 ? sum_lq     / (int32_t)fl_node_count : 0;
      int32_t avg_w_energy = fl_node_count > 0 ? sum_energy / (int32_t)fl_node_count : 0;
  
      LOG_INFO("Received request '%.*s' from ", datalen, (char *) data);
      LOG_INFO_6ADDR(sender_addr);
      LOG_INFO_("\n");
  #ifdef FEDERATION
    #ifdef SARSA_LOGGING
      bool _cpu_on = energest_current_mode[ENERGEST_TYPE_CPU];
      if(_cpu_on) ENERGEST_OFF(ENERGEST_TYPE_CPU);
      LOG_INFO("FL-AGG | seq: %"PRIu32" | n=%u | avg_lq: %ld | avg_eng: %ld | from ",
              pl->seq, (unsigned)fl_node_count, (long)avg_w_lq, (long)avg_w_energy);
      LOG_INFO_6ADDR(sender_addr);
      LOG_INFO_("\n");
      if(_cpu_on) ENERGEST_ON(ENERGEST_TYPE_CPU);
    #endif
  #endif /* SARSA_LOGGING */
  #if WITH_SERVER_REPLY
    LOG_INFO("Sending response.\n");
    udp_fed_reply_t reply;
    reply.magic = FED_MAGIC;
    reply.agg_w_lq    = avg_w_lq;
    reply.agg_w_energy = avg_w_energy;
    reply.num_nodes   = fl_node_count;
    simple_udp_sendto(&udp_conn, &reply, sizeof(reply), sender_addr);
  #endif /* WITH_SERVER_REPLY */
  } else {
    // Non-federation packet received
    LOG_INFO("Received request '%.*s' from ", datalen, (char *) data);
    LOG_INFO_6ADDR(sender_addr);
    LOG_INFO_("\n");

    #ifdef WITH_SERVER_REPLY
      LOG_INFO("Sending response.\n");
      simple_udp_sendto(&udp_conn, data, datalen, sender_addr);
    #endif
  }
  #else
    LOG_INFO("Received request '%.*s' from ", datalen, (char *) data);
    LOG_INFO_6ADDR(sender_addr);
    LOG_INFO_("\n");

    #ifdef WITH_SERVER_REPLY
      LOG_INFO("Sending response.\n");
      simple_udp_sendto(&udp_conn, data, datalen, sender_addr);
    #endif

  #endif
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(udp_server_process, ev, data)
{
  PROCESS_BEGIN();

  /* Initialize DAG root */
  NETSTACK_ROUTING.root_start();

  /* Initialize UDP connection */
  simple_udp_register(&udp_conn, UDP_SERVER_PORT, NULL,
                      UDP_CLIENT_PORT, udp_rx_callback);

  PROCESS_END();
}
/*---------------------------------------------------------------------------*/

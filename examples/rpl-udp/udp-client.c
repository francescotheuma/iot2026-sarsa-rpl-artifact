#include "contiki.h"
#include "net/routing/routing.h"
#include "random.h"
#include "net/netstack.h"
#include "net/ipv6/simple-udp.h"
#include <stdint.h>
#include <inttypes.h>
#include <battery.h>
#include "energest.h"
#include <stddef.h> //for federation fairness with other protocols

#include "sys/log.h"
#define LOG_MODULE "App"
#define LOG_LEVEL LOG_LEVEL_INFO

#define WITH_SERVER_REPLY  1
#define UDP_CLIENT_PORT	8765
#define UDP_SERVER_PORT	5678

#define SEND_INTERVAL		  (10 * CLOCK_SECOND)

#ifdef FEDERATION
  #define FED_MAGIC 0xFA
  #ifdef FED_CONF_THRESHOLD
    #define FED_THRESHOLD FED_CONF_THRESHOLD
  #else
    #define FED_THRESHOLD 10 
  #endif
#endif

#ifdef FEDERATION
  /* Federated learning payload structs — must match udp-server.c */
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

  extern void sarsa_get_weights(int32_t *w_lq, int32_t *w_energy);
  extern void sarsa_apply_federated_weights(int32_t agg_w_lq, int32_t agg_w_energy);

#endif

static struct simple_udp_connection udp_conn;
static uint32_t rx_count = 0;
static int32_t federation_counter = 0;

/*---------------------------------------------------------------------------*/
PROCESS(udp_client_process, "UDP client");
AUTOSTART_PROCESSES(&udp_client_process);
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

  LOG_INFO("Received response '%.*s' from ", datalen, (char *) data);
  LOG_INFO_6ADDR(sender_addr);
  #ifdef FEDERATION
    if(datalen == sizeof(udp_fed_reply_t)) {
      const udp_fed_reply_t *reply = (const udp_fed_reply_t *)data;
      
      if(reply->magic == FED_MAGIC) {
        sarsa_apply_federated_weights(reply->agg_w_lq, reply->agg_w_energy);
        #ifdef SARSA_LOGGING
            ENERGEST_OFF(ENERGEST_TYPE_CPU);
            LOG_INFO_("\n");
            LOG_INFO("FL-UPDATE | agg_lq: %ld | agg_eng: %ld | n=%u | from ",
                    (long)reply->agg_w_lq, (long)reply->agg_w_energy, (unsigned)reply->num_nodes);
            LOG_INFO_6ADDR(sender_addr);
            ENERGEST_ON(ENERGEST_TYPE_CPU);
        #endif /* SARSA_LOGGING */

      }
      
    }
  #endif
  #if LLSEC802154_CONF_ENABLED
    LOG_INFO_(" LLSEC LV:%d", uipbuf_get_attr(UIPBUF_ATTR_LLSEC_LEVEL));
  #endif
  LOG_INFO_("\n");
  rx_count++;
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(udp_client_process, ev, data)
{
  static struct etimer periodic_timer;
  uip_ipaddr_t dest_ipaddr;
  static uint32_t tx_count;
  static uint32_t missed_tx_count;


  PROCESS_BEGIN();

  battery_init(); // To log battery for graph comparisons between OFs

  /* Initialize UDP connection */
  simple_udp_register(&udp_conn, UDP_CLIENT_PORT, NULL,
                      UDP_SERVER_PORT, udp_rx_callback);

  etimer_set(&periodic_timer, random_rand() % SEND_INTERVAL);
  while(1) {
    PROCESS_WAIT_EVENT_UNTIL(etimer_expired(&periodic_timer));

    if(NETSTACK_ROUTING.node_is_reachable() &&
        NETSTACK_ROUTING.get_root_ipaddr(&dest_ipaddr)) {

      /* Print statistics every 10th TX */
      if(tx_count % 10 == 0) {
        LOG_INFO("Tx/Rx/MissedTx: %" PRIu32 "/%" PRIu32 "/%" PRIu32 "\n",
                 tx_count, rx_count, missed_tx_count);
      }

      /* Send to DAG root */
      LOG_INFO("Sending request %"PRIu32" to ", tx_count);
      LOG_INFO_6ADDR(&dest_ipaddr);
      LOG_INFO_("\n");
      #ifdef FEDERATION
        int32_t current_w_lq, current_w_energy;
        sarsa_get_weights(&current_w_lq, &current_w_energy);

        // Only transmit if deviation exceeds theshold
        if(federation_counter >= FED_THRESHOLD) {
          // Send app data + FL weights
          udp_fed_payload_t payload;
          payload.magic = FED_MAGIC;
          payload.seq = tx_count;
          payload.w_lq = current_w_lq;
          payload.w_energy = current_w_energy;

          snprintf(payload.app_data, sizeof(payload.app_data), "hello %" PRIu32 "", tx_count);

          // offset magic
          size_t exact_size = offsetof(udp_fed_payload_t, app_data) + strlen(payload.app_data) + 1;
          simple_udp_sendto(&udp_conn, &payload, exact_size, &dest_ipaddr);

          federation_counter = 0;
        }
        else{
          static char str[32];
          snprintf(str, sizeof(str), "hello %" PRIu32 "", tx_count);
          simple_udp_sendto(&udp_conn, str, strlen(str), &dest_ipaddr);
          federation_counter++;
        }

      #else
        static char str[32];
        snprintf(str, sizeof(str), "hello %" PRIu32 "", tx_count);
        simple_udp_sendto(&udp_conn, str, strlen(str), &dest_ipaddr);
      #endif
      tx_count++;
    } else {
      LOG_INFO("Not reachable yet\n");
      if(tx_count > 0) {
        missed_tx_count++;
      }
    }

    /* Add some jitter */
    etimer_set(&periodic_timer, SEND_INTERVAL
      - CLOCK_SECOND + (random_rand() % (2 * CLOCK_SECOND)));
  }

  PROCESS_END();
}
/*---------------------------------------------------------------------------*/

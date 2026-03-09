#include "energest.h"
#include "sys/clock.h"
#include "sys/ctimer.h"
#include "sys/log.h"
#include "net/linkaddr.h"

#define LOG_MODULE "Battery"
#define LOG_LEVEL LOG_LEVEL_INFO

/* for energest battery drain*/
#define DRAIN_MAGNITUDE 500
#define BATTERY_LOG_INTERVAL (10 * CLOCK_SECOND)

static struct ctimer battery_timer;
static uint8_t battery_log_initialized = 0;

/* Function to get battery level*/
 uint8_t 
 get_local_energy_est(void) {
  energest_flush(); // forces update of tick counts
  
  uint64_t tx_ticks = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  uint64_t rx_ticks = energest_type_time(ENERGEST_TYPE_LISTEN);
  uint64_t cpu_ticks = energest_type_time(ENERGEST_TYPE_CPU);
  
  uint64_t simulated_rx_ticks = rx_ticks / 100;
  uint64_t total_consumption = (tx_ticks + simulated_rx_ticks + cpu_ticks) * DRAIN_MAGNITUDE;
  
  uint64_t battery_max = 1000000000ULL; //Crazy math
  long drain = total_consumption / (battery_max / 100);
  long remaining = 100 - drain;

  if(remaining < 0) return 0;
  if(remaining > 100) return 100;

  return (uint8_t)remaining;
}

static void
battery_log_callback(void *ptr)
{
    uint8_t batt = get_local_energy_est();
    uint8_t node_id = linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    LOG_INFO("BATTERY_SAMPLE: node=%d, batt=%d\n", node_id, batt);
    ctimer_reset(&battery_timer);
}

void
battery_init(void){
    if(!battery_log_initialized){
        ctimer_set(&battery_timer, BATTERY_LOG_INTERVAL,battery_log_callback,NULL);
    }
}
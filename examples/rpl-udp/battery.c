#include "contiki.h"
#include "energest.h"

/* for energest battery drain*/
#define DRAIN_MAGNITUDE 500

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
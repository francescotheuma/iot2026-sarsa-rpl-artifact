#include "energest.h"
#include "sys/clock.h"
#include "sys/ctimer.h"
#include "sys/log.h"
#include "net/linkaddr.h"
#include "net/netstack.h"
#include "net/routing/routing.h"

#define LOG_MODULE "Battery"
#define LOG_LEVEL LOG_LEVEL_INFO

/* for energest battery drain*/
#define DRAIN_MAGNITUDE 200
#define BATTERY_LOG_INTERVAL (10 * CLOCK_SECOND)

static struct ctimer battery_timer;
static uint8_t battery_log_initialized = 0;

typedef struct{
    uint8_t percentage;
    uint8_t tx_ticks;
    uint64_t rx_ticks;
    uint64_t cpu_ticks;
} battery_stats_t;

battery_stats_t
get_detailed_energy_est(void){
    energest_flush();

    battery_stats_t stats;
    stats.tx_ticks = energest_type_time(ENERGEST_TYPE_TRANSMIT);
    stats.rx_ticks = energest_type_time(ENERGEST_TYPE_LISTEN);
    stats.cpu_ticks = energest_type_time(ENERGEST_TYPE_CPU);

    uint64_t simulated_rx_ticks= stats.rx_ticks / 100;
    uint64_t total_consumption = (stats.tx_ticks + simulated_rx_ticks + stats.cpu_ticks) * DRAIN_MAGNITUDE;

    uint64_t battery_max = 1000000000ULL; 
    long drain = total_consumption / (battery_max / 100);
    long remaining = 100 - drain;

    if(remaining < 0) remaining = 0;
    if(remaining > 100) remaining = 100;

    if(remaining == 0){
        NETSTACK_MAC.off();
        NETSTACK_ROUTING.leave_network();

        return stats;
    }

    stats.percentage = (uint8_t)remaining;
    return stats;
}
/* Function to get battery level*/
 uint8_t 
 get_local_energy_est(void) {

  return get_detailed_energy_est().percentage;
}

static void
battery_log_callback(void *ptr)
{
    battery_stats_t stats = get_detailed_energy_est();
    uint8_t node_id = linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    
    // We cast to unsigned long for safe printf formatting in Contiki
    LOG_INFO("BATTERY_SAMPLE: node=%d, batt=%d, TX=%lu, RX=%lu, CPU=%lu\n", 
             node_id, 
             stats.percentage, 
             (unsigned long)stats.tx_ticks, 
             (unsigned long)stats.rx_ticks, 
             (unsigned long)stats.cpu_ticks);

    ctimer_reset(&battery_timer);
}

void
battery_init(void){
    if(!battery_log_initialized){
        ctimer_set(&battery_timer, BATTERY_LOG_INTERVAL,battery_log_callback,NULL);
        battery_log_initialized = 1;
    }
}
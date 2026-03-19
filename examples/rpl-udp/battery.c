#include "energest.h"
#include "sys/clock.h"
#include "sys/ctimer.h"
#include "sys/log.h"
#include "net/linkaddr.h"
#include "net/netstack.h"
#include "net/routing/routing.h"
#include "sys/node-id.h"

#define LOG_MODULE "Battery"
#define LOG_LEVEL LOG_LEVEL_INFO

// Hardware power ratios
#define COST_TX 10

#ifdef CONF_COST_RX
    #define COST_RX CONF_COST_RX
#endif

#define COST_CPU 1

// Simulated MAC layer Duty Cycle
#define DUTY_CYCLE_PERCENT 5

/* for energest battery drain*/
#ifdef CONF_DRAIN_MAGNITUDE
    #define DRAIN_MAGNITUDE CONF_DRAIN_MAGNITUDE
#else
    #define DRAIN_MAGNITUDE 10
#endif

#define BATTERY_SIZE 1000000000ULL // 1 billion ticks represents a full battery for our estimation
#define BATTERY_LOG_INTERVAL (10 * CLOCK_SECOND)

static struct ctimer battery_timer;
static uint8_t battery_log_initialized = 0;
static int has_logged_depletion = 0; // Flag to track if depletion has been logged (to avoid spam)

typedef struct{
    uint8_t percentage;
    uint64_t tx_ticks;
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

    uint64_t duty_cycled_rx_ticks = (stats.rx_ticks * DUTY_CYCLE_PERCENT) / 100;

    uint64_t weighted_tx = stats.tx_ticks * COST_TX;
    uint64_t weighted_rx = duty_cycled_rx_ticks * COST_RX;
    uint64_t weighted_cpu = stats.cpu_ticks * COST_CPU;


    uint64_t total_consumption = (weighted_tx + weighted_rx + weighted_cpu) * DRAIN_MAGNITUDE;

    uint64_t battery_max = BATTERY_SIZE; 
    long drain = total_consumption / (battery_max / 100);
    
    int initial_offset = 0;
    switch(node_id){
        case 2: initial_offset = 70;break;
        case 3: initial_offset = 30;break;
        case 4: initial_offset = 0;break;
        default: initial_offset = 0;break;
    }
    long remaining = 100 - initial_offset - drain;

    if(remaining < 0) remaining = 0;
    if(remaining > 100) remaining = 100;

    if(remaining == 0){
        if(has_logged_depletion == 0){
            LOG_INFO("Battery depleted. Shutting down node.\n");
            NETSTACK_MAC.off();
            NETSTACK_ROUTING.leave_network();

            has_logged_depletion = 1; // Set flag to indicate depletion has been logged

            return stats;
        }
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
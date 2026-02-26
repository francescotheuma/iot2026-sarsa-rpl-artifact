#include "net/routing/rpl-lite/rpl.h"
#include "net/nbr-table.h"
#include "net/link-stats.h"
#include "sys/log.h"
#include "sys/clock.h" 
#include "sys/energest.h"
#include "random.h" 

/* for energest battery drain*/
#define DRAIN_MAGNITUDE 500

/* Log configuration */
#define LOG_MODULE "RPL-SARSA"
#define LOG_LEVEL LOG_LEVEL_INFO

#ifndef RPL_OCP_SARSA
#define RPL_OCP_SARSA 10
#endif

#ifndef NBR_TABLE_REASON_RPL_LITE
#define NBR_TABLE_REASON_RPL_LITE NBR_TABLE_REASON_MAC
#endif

/* --- ML CONSTANTS --- */
#define ALPHA 20   /* Learning Rate (0.20) */
#define GAMMA 90   /* Discount Factor (0.90) */

#define MAX_LINK_METRIC     512   
#define MAX_PATH_COST       32768 

/* --- POLICY WEIGHTS --- */
/* We renamed w_etx to w_lq (Weight of Link Quality) because we are 
 * converting the ETX cost into a positive utility score. */
static int32_t w_energy = 50; 
static int32_t w_lq = 50;

// Struct to house the SARSA-related node values
typedef struct {
  int32_t q_value;      
  uint8_t energy_level; 
} sarsa_nbr_t;

NBR_TABLE(sarsa_nbr_t, sarsa_neighbors);

/* Function to get battery level*/
static uint8_t 
get_local_energy_est(void) {
  energest_flush(); // forces update of tick counts
  
  uint64_t tx_ticks = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  uint64_t rx_ticks = energest_type_time(ENERGEST_TYPE_LISTEN);
  uint64_t cpu_ticks = energest_type_time(ENERGEST_TYPE_CPU);
  
  uint64_t simulated_rx_ticks = rx_ticks / 100;
  uint64_t total_consumption = (tx_ticks + simulated_rx_ticks + cpu_ticks) * DRAIN_MAGNITUDE;
  
  long battery_max = 1000000000ULL; //Crazy math
  long drain = total_consumption / (battery_max / 100);
  long remaining = 100 - drain;

  if(remaining < 0) return 0;
  if(remaining > 100) return 100;

  return (uint8_t)remaining;
}

/*---------------------------------------------------------------------------*/
static void
reset(void)
{
  LOG_INFO("Resetting SARSA LFA OF and initializing Q-Table\n");
  nbr_table_register(sarsa_neighbors, NULL);
}

/*---------------------------------------------------------------------------*/
static sarsa_nbr_t *
get_sarsa_data(rpl_nbr_t *nbr)
{
  if(nbr == NULL) return NULL;

  const linkaddr_t *lladdr = rpl_neighbor_get_lladdr(nbr);
  sarsa_nbr_t *s_data = nbr_table_get_from_lladdr(sarsa_neighbors, lladdr);

  if(s_data == NULL) {
    s_data = nbr_table_add_lladdr(sarsa_neighbors, lladdr, NBR_TABLE_REASON_RPL_LITE, NULL);
    if(s_data != NULL) {
      s_data->q_value = 0;
      s_data->energy_level = 100; 
    }
  }
  return s_data;
}

/*---------------------------------------------------------------------------*/
static uint16_t
nbr_link_metric(rpl_nbr_t *nbr)
{
  const struct link_stats *stats = rpl_neighbor_get_link_stats(nbr);
  return stats != NULL ? stats->etx : 0xffff;
}

/*---------------------------------------------------------------------------*/
static void
update_q_value(rpl_nbr_t *nbr, sarsa_nbr_t *data)
{
  if(nbr == NULL || data == NULL) return;

  /* --- FEATURES --- */
  int32_t f_energy = (int32_t)data->energy_level; 

  /* 1. Scale ETX so that 1.0 (512) is the base, and 5.0 (2560) is 'terrible' */
  int32_t raw_etx = (int32_t)nbr_link_metric(nbr); 

  /* 2. Convert to a 0-100 scale where 100 is BEST. 
    We use 512 as the 'perfect' floor. */
  int32_t f_link_quality;
  if(raw_etx <= 512) {
      f_link_quality = 100; // Perfect link
  } else if(raw_etx >= 2560) {
      f_link_quality = 0;   // Anything worse than ETX 5.0 is 'trash'
  } else {
      // Math to slide between 100 and 0
      f_link_quality = 100 - (((raw_etx - 512) * 100) / (2560 - 512));
  }

  /* --- PREDICTION --- */
  int32_t old_predicted_q = data->q_value; 

  /* --- REWARD & FUTURE VALUE --- */
  int32_t total_weight = w_energy + w_lq;
  if (total_weight == 0) total_weight = 1; 
  int32_t reward = ((w_energy * f_energy) + (w_lq * f_link_quality)) / total_weight;

  int32_t future_value = 0;
  if(nbr->rank > 0 && nbr->rank < 65535) {
      future_value = 25600 / (int32_t)nbr->rank;
      if(future_value > 100) future_value = 100;
  }

  /* --- TD ERROR --- */
  int32_t target = (((100 - GAMMA) * reward) + (GAMMA * future_value)) / 100;
  int32_t td_error = target - old_predicted_q; 

  /* --- CONDITIONAL LEARNING (Proper SARSA) --- */
  /* Only update the global weights if this neighbor is our chosen action (parent) */
  if(nbr == curr_instance.dag.preferred_parent) {
      
      // Decay
      w_energy = w_energy - (w_energy >> 6);
      w_lq = w_lq - (w_lq >> 6);

      // Update weights based on the experience with THIS parent
      w_energy = w_energy + ((ALPHA * td_error * f_energy) / 1000);
      w_lq = w_lq + ((ALPHA * td_error * f_link_quality) / 1000);

      // Soft Floor
      if(w_energy < 10) w_energy = 10;
      if(w_lq < 10) w_lq = 10;
      
      LOG_INFO("LEARNING (On-Policy): Nbr %02x | W_E: %d, W_LQ: %d| Batt: %u%%\n", 
               rpl_neighbor_get_lladdr(nbr)->u8[LINKADDR_SIZE - 1], (int)w_energy, (int)w_lq, (unsigned int)get_local_energy_est());
  }

  /* --- SAVE Q-VALUE --- */
  /* Always update the neighbor's individual Q-value for comparison purposes */
  total_weight = w_energy + w_lq; 
  data->q_value = ((w_energy * f_energy) + (w_lq * f_link_quality)) / total_weight; 
}

/*---------------------------------------------------------------------------*/
static uint16_t
nbr_path_cost(rpl_nbr_t *nbr)
{
  if(nbr == NULL) return 0xffff;
  uint32_t base = nbr->rank;
  return MIN(base + nbr_link_metric(nbr), 0xffff);
}

/*---------------------------------------------------------------------------*/
static rpl_rank_t
rank_via_nbr(rpl_nbr_t *nbr)
{
  if(nbr == NULL) return RPL_INFINITE_RANK;
  uint16_t path_cost = nbr_path_cost(nbr);
  return MAX(MIN((uint32_t)nbr->rank + curr_instance.min_hoprankinc, RPL_INFINITE_RANK), path_cost);
}

/*---------------------------------------------------------------------------*/
static int
nbr_has_usable_link(rpl_nbr_t *nbr)
{
  return nbr_link_metric(nbr) <= MAX_LINK_METRIC;
}

/*---------------------------------------------------------------------------*/
static int
nbr_is_acceptable_parent(rpl_nbr_t *nbr)
{
  return nbr_has_usable_link(nbr) && nbr_path_cost(nbr) <= MAX_PATH_COST;
}

/*---------------------------------------------------------------------------*/
static rpl_nbr_t *
best_parent(rpl_nbr_t *p1, rpl_nbr_t *p2)
{
  int p1_ok = p1 != NULL && nbr_is_acceptable_parent(p1);
  int p2_ok = p2 != NULL && nbr_is_acceptable_parent(p2);

  if(!p1_ok) return p2_ok ? p2 : NULL;
  if(!p2_ok) return p1_ok ? p1 : NULL;

  sarsa_nbr_t *d1 = get_sarsa_data(p1);
  sarsa_nbr_t *d2 = get_sarsa_data(p2);

  if(p1 != NULL && d1 != NULL) d1->energy_level = p1->mc.obj.energy.energy_est;
  if(p2 != NULL && d2 != NULL) d2->energy_level = p2->mc.obj.energy.energy_est;

  if(d1) update_q_value(p1, d1);
  if(d2) update_q_value(p2, d2);

  if(d1 == NULL) return p1; 
  if(d2 == NULL) return p2;

  if(random_rand() % 100 < 10) {
      LOG_INFO("SARSA EXPLORATION (10%%): Trying random route!\n");
      return (random_rand() % 2 == 0) ? p1 : p2;
  }

  if(p1 == curr_instance.dag.preferred_parent) {
      return (d1->q_value + 5 >= d2->q_value) ? p1 : p2; 
  }
  if(p2 == curr_instance.dag.preferred_parent) {
      return (d2->q_value + 5 >= d1->q_value) ? p2 : p1;
  }

  return (d1->q_value > d2->q_value) ? p1 : p2;
}

/*---------------------------------------------------------------------------*/
static void
update_metric_container(void)
{
  curr_instance.mc.type = RPL_DAG_MC_ENERGY;
  curr_instance.mc.length = sizeof(curr_instance.mc.obj.energy);
  curr_instance.mc.obj.energy.energy_est = get_local_energy_est();
  curr_instance.mc.obj.energy.flags = RPL_DAG_MC_ENERGY_TYPE_BATTERY << RPL_DAG_MC_ENERGY_TYPE;
}

/*---------------------------------------------------------------------------*/
rpl_of_t rpl_sarsa = {
  reset,
  nbr_link_metric,
  nbr_has_usable_link,
  nbr_is_acceptable_parent,
  nbr_path_cost,
  rank_via_nbr,
  best_parent,
  update_metric_container,
  RPL_OCP_SARSA
};
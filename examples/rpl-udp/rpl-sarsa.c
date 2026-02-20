#include "net/routing/rpl-lite/rpl.h"
#include "net/nbr-table.h"
#include "net/link-stats.h"
#include "sys/log.h"
#include "sys/clock.h" /* Required for clock_seconds() */
#include "sys/energest.h"

/* for energest*/
#define DRAIN_MAGNITUDE 1000000

/* Log configuration */
#define LOG_MODULE "RPL"
#define LOG_LEVEL LOG_LEVEL_RPL

/* Ensure OCP is defined if not already in rpl-const.h */
#ifndef RPL_OCP_SARSA
#define RPL_OCP_SARSA 10
#endif

/* FIX FOR COMPILATION ERROR: Define the reason if missing */
#ifndef NBR_TABLE_REASON_RPL_LITE
#define NBR_TABLE_REASON_RPL_LITE NBR_TABLE_REASON_MAC
#endif

/* SARSA Constants (Integer Math) */
#define ALPHA 20   /* Learning Rate 0.2 */
#define GAMMA 90   /* Discount Factor 0.9 */

/* Constants from MRHOF for basic RPL compatibility */
#define MAX_LINK_METRIC     512   
#define MAX_PATH_COST       32768 

/*---------------------------------------------------------------------------*/
/* SARSA NEIGHBOR STORAGE */
typedef struct {
  int32_t q_value;      /* The learned routing value */
  uint8_t energy_level; /* The neighbor's battery percentage (0-100) */
} sarsa_nbr_t;

/* Define the memory table for these structures */
NBR_TABLE(sarsa_nbr_t, sarsa_neighbors);

/*---------------------------------------------------------------------------*/
/* Helper to get local battery for the MC - PLACED AT TOP TO AVOID TYPE ERRORS */
static uint8_t 
get_local_energy_est(void) {
  /* 1. Update all Energest values to the current moment */
  energest_flush();

  /* 2. Get the total time the radio has been active (TX + RX) */
  /* These values are in 'ticks' */
  uint64_t tx_ticks = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  uint64_t rx_ticks = energest_type_time(ENERGEST_TYPE_LISTEN);
  
  /* 3. Calculate "Cost" with your requested magnitude increase */
  /* We scale it so that simulation activity actually impacts the battery */
  uint64_t total_consumption = (tx_ticks + rx_ticks) * DRAIN_MAGNITUDE;

  /* 4. Convert to a 0-100 percentage */
  /* In a real scenario, you'd divide by a battery capacity constant */
  /* For simulation, we subtract from 100 and floor at 0 */
  long battery_max = 1000000000ULL; // Representing a hypothetical capacity
  long remaining = 100 - (total_consumption / (battery_max / 100));

  if(remaining < 0) return 0;
  if(remaining > 100) return 100;

  return (uint8_t)remaining;
}
/*---------------------------------------------------------------------------*/
static void
reset(void)
{
  LOG_INFO("Resetting SARSA OF and initializing Q-Table\n");
  nbr_table_register(sarsa_neighbors, NULL);
}

/*---------------------------------------------------------------------------*/
/* Helper: Get our custom SARSA data for a specific RPL neighbor */
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
      s_data->energy_level = 100; /* Default to full battery */
      LOG_DBG("SARSA: New neighbor detected, initialized Q=0\n");
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
/* The Heart of SARSA: Update Q-values based on recent performance */
static void
update_q_value(rpl_nbr_t *nbr, sarsa_nbr_t *data)
{
  if(nbr == NULL || data == NULL) return;

  /* --- INPUTS --- */
  uint16_t current_etx = nbr_link_metric(nbr); 
  int local_batt = (int)get_local_energy_est(); 
  int nbr_batt = (int)data->energy_level; 

  /* --- DYNAMIC WEIGHTING --- */
  int32_t w_etx = local_batt;
  int32_t w_energy = 100 - local_batt;

  /* --- COMPONENT REWARDS --- */
  int32_t r_etx = (500 - (int32_t)current_etx);
  if(r_etx < 0) r_etx = 0;

  int32_t r_energy = (int32_t)nbr_batt * 5;

  /* --- TOTAL WEIGHTED REWARD --- */
  int32_t total_reward = ((r_etx * w_etx) + (r_energy * w_energy)) / 100;

  /* --- FUTURE PREDICTION (RANK) --- */
  int32_t future_value = 0;
  if(nbr->rank < 65535) {
     future_value = (5000 - (int32_t)nbr->rank) / 10; 
  }

  /* --- SARSA UPDATE --- */
  int32_t target = total_reward + (GAMMA * future_value / 100); 
  int32_t td_error = target - data->q_value; 
  data->q_value = data->q_value + (ALPHA * td_error / 100); 

  /* FIX: Use LINKADDR_SIZE instead of .len */
  LOG_INFO("SARSA Update: Nbr %02x | LocalBatt %d%% | NbrBatt %d%% | Weights %ld/%ld | New Q %ld\n", 
           rpl_neighbor_get_lladdr(nbr)->u8[LINKADDR_SIZE - 1],
           local_batt, nbr_batt, (long)w_etx, (long)w_energy, (long)data->q_value);
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

  /* SYNC: Pull latest Energy from Metric Container if available */
  if(p1 != NULL && d1 != NULL) {
    d1->energy_level = p1->mc.obj.energy.energy_est;
  }
  if(p2 != NULL && d2 != NULL) {
    d2->energy_level = p2->mc.obj.energy.energy_est;
  }

  if(d1) update_q_value(p1, d1);
  if(d2) update_q_value(p2, d2);

  if(d1 == NULL) return p1; 
  if(d2 == NULL) return p2;

  /* DECIDE with Hysteresis */
  if(p1 == curr_instance.dag.preferred_parent) {
      return (d1->q_value + 20 >= d2->q_value) ? p1 : p2;
  }
  if(p2 == curr_instance.dag.preferred_parent) {
      return (d2->q_value + 20 >= d1->q_value) ? p2 : p1;
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
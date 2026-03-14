#include "net/routing/rpl-lite/rpl.h"
#include "net/nbr-table.h"
#include "net/link-stats.h"
#include "sys/log.h"
#include "sys/clock.h" 
#include "random.h" 
#include "battery.h"

/* Log configuration */
#define LOG_MODULE "RPL-SARSA"
#define LOG_LEVEL LOG_LEVEL_INFO

#ifndef NBR_TABLE_REASON_RPL_LITE
#define NBR_TABLE_REASON_RPL_LITE NBR_TABLE_REASON_MAC
#endif

/* --- ML CONSTANTS --- */
#define ALPHA 2   /* Learning Rate (0.20) */
#define GAMMA 80   /* Discount Factor (0.90) */

#define MAX_LINK_METRIC     512   
#define MAX_PATH_COST       32768 

// Struct to house the SARSA-related node values
typedef struct {
  int32_t q_value;      
  int32_t energy_level;
  /* Weights per neighbour*/
  int32_t w_lq; 
  int32_t w_energy;
} sarsa_nbr_t;

NBR_TABLE(sarsa_nbr_t, sarsa_neighbors); // macro that allocates array of memory for the neighbours


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
      s_data->q_value = 100; // Optimistic initialisation
      s_data->w_lq = 50;
      s_data->w_energy = 50;
      s_data->energy_level = 100; // to prevent initial bias against new neighbours with unknown energy levels
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
static void
update_q_value(rpl_nbr_t *nbr, sarsa_nbr_t *data)
{
  if(nbr == NULL || data == NULL) return; 

  int32_t f_energy = (int32_t)data->energy_level;
  int32_t raw_etx = (int32_t)nbr_link_metric(nbr);
  int32_t f_link_quality;

  // Normalise ETX from 0-100

  if(raw_etx <= 512) f_link_quality = 100;
  else if (raw_etx >=2560) f_link_quality = 0;
  else f_link_quality = 100 - (((raw_etx - 512) * 100) >> 11); // divide by 2048 (2^11 = 2048) with bit shift

  int32_t total_weight = data->w_energy + data->w_lq;


  /* Comine features into q-value for neighbour */
  data->q_value = ((data->w_energy * f_energy) + (data->w_lq * f_link_quality)) / total_weight;
}
/*---------------------------------------------------------------------------*/

#include "net/ipv6/uip-ds6-nbr.h" // for callback function to convert MAC address to RPL neighbour

/*---------------------------------------------------------------------------*/
void sarsa_mac_reward_callback(const linkaddr_t *lladdr, int status, int numtx) 
{

  rpl_instance_t *instance = rpl_get_default_instance();

  // Check if node is Root
  if(instance != NULL && instance->used) {
    if(instance->dag.rank == ROOT_RANK){
      return; // Root doesn't learn, it just serves as a sink
    }
  }

  if(lladdr == NULL || linkaddr_cmp(lladdr, &linkaddr_null)) return;

  /* 1. Safely convert MAC address to RPL Neighbor */
  uip_ds6_nbr_t *ds6_nbr = uip_ds6_nbr_ll_lookup((const uip_lladdr_t *)lladdr);
  if(ds6_nbr == NULL) return;
  rpl_nbr_t *nbr = rpl_neighbor_get_from_ipaddr(&ds6_nbr->ipaddr);
  if(nbr == NULL) return;

  /* 2. Get SARSA data for the neighbour transmitted to*/
  sarsa_nbr_t *data = get_sarsa_data(nbr);
  if(data == NULL) return;

  /* 3. The True Environmental Reward */
  int32_t reward = 0;
  int32_t parent_battery = (int32_t)data->energy_level;

  if(status == MAC_TX_OK) {
    // Reward changes based on parent battery level to encourage energy balancing
      reward = parent_battery;  
      
      if(numtx > 1){
        reward -= (10*numtx);
      }
  } else {
      reward = -20; // Massive penalty for dropped packet
  }

  /* 4. Extract State Features */
  int32_t raw_etx = (int32_t)nbr_link_metric(nbr); 
  int32_t f_link_quality;
  if(raw_etx <= 512) f_link_quality = 100;
  else if(raw_etx >= 2560) f_link_quality = 0;
  else f_link_quality = 100 - (((raw_etx - 512) * 100) >> 11); // divide by 2048 (2^11 = 2048) with bit shift

  int32_t f_energy = parent_battery;

  int32_t old_predicted_q = data->q_value; 

  /* 5. Future Value */
  int32_t future_value = 0;
  if(nbr->rank < RPL_INFINITE_RANK) {
      future_value = 100 - (((int32_t)nbr->rank * 100) >> 15); // normalise rank to 0-100 with bit shift (divide by 32768);
      if(future_value < 0) future_value = 0;
  }

  /* 6. Calculate True TD Error */
  int32_t target = (((100 - GAMMA) * reward) + (GAMMA * future_value)) / 100;
  int32_t td_error = target - old_predicted_q; 

  /* 7. Update Global Policy Weights */
  data->w_lq = data->w_lq + ((ALPHA * td_error * f_link_quality) / 100); // divide by 100 to avoid floating point math
  data->w_energy = data->w_energy + ((ALPHA * td_error * f_energy) / 100);

  /* Soft bounds to prevent weights from exploding/dying */
  if(data->w_lq < 10) data->w_lq = 10;
  if(data->w_energy < 10) data->w_energy = 10;
  if (data->w_lq > 200) data->w_lq = 200;
  if (data->w_energy > 200) data->w_energy = 200;


  uint16_t nbr_id = rpl_neighbor_get_lladdr(nbr)->u8[LINKADDR_SIZE - 1];

  LOG_INFO("MAC REWARD: %s | Parent: %d | Rew: %d | TD_Err: %d | W_LQ: %d | W_Energy: %d | My_batt: %d | Parent_batt: %d\n",
           (status == MAC_TX_OK) ? "OK" : "FAIL",
           (int)nbr_id, (int)reward, (int)td_error, (int)data->w_lq, (int)data->w_energy, (get_local_energy_est()),(int)parent_battery);
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

  // EXPLORATION
  if(random_rand() % 100 < 2) { 
      LOG_INFO("SARSA EXPLORATION (2%%): Trying random route!\n");
      return ((random_rand() & 1) == 0) ? p1 : p2; // check least significant bit for random choice (odd or even)
  }

  // +5 is a small bias to prevent Hysterisis
  if(p1 == curr_instance.dag.preferred_parent) {
      return (d1->q_value + 15 >= d2->q_value) ? p1 : p2; 
  }
  if(p2 == curr_instance.dag.preferred_parent) {
      return (d2->q_value + 15 >= d1->q_value) ? p2 : p1;
  }

  return (d1->q_value > d2->q_value) ? p1 : p2;
}

/*---------------------------------------------------------------------------*/
static void
update_metric_container(void)
{
  curr_instance.mc.type = RPL_DAG_MC_ENERGY;
  curr_instance.mc.length = sizeof(curr_instance.mc.obj.energy);

  // Root always has 100% battery
  if(curr_instance.dag.rank == ROOT_RANK){
      curr_instance.mc.obj.energy.energy_est = 100;
  }
  else{
      curr_instance.mc.obj.energy.energy_est = get_local_energy_est();
  }

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
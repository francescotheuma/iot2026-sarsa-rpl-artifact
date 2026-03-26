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
#ifdef SARSA_CONF_ALPHA
  #define ALPHA SARSA_CONF_ALPHA
#else
  #define ALPHA 10
#endif

#ifdef SARSA_CONF_GAMMA
  #define GAMMA SARSA_CONF_GAMMA
#else
  #define GAMMA 80
#endif

#define MAX_LINK_METRIC     512   
#define MAX_PATH_COST       32768 
#define MAX_WEIGHT 1000
#define MIN_WEIGHT -1000

#define LEARNING_BATCH_SIZE 7
#define SARSA_HYSTERESIS 0

// Struct to house the SARSA-related node values
typedef struct {
  int32_t energy_level;
  int16_t next_action_q;  
  uint8_t learning_counter;
} sarsa_nbr_t;

// GLOBAL WEIGHTS
int32_t global_w_lq = 50;
int32_t global_w_energy = 50;

NBR_TABLE(sarsa_nbr_t, sarsa_neighbors); // macro that allocates array of memory for the neighbours


/*---------------------------------------------------------------------------*/
static void
reset(void)
{

  #ifdef SARSA_LOGGING
    LOG_INFO("Resetting SARSA LFA OF and initializing Q-Table\n");
  #endif
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
      s_data->energy_level = 100; // to prevent initial bias against new neighbours with unknown energy levels
      s_data->next_action_q = 100; //Optimistic initialisation for next action Q-value
      s_data->learning_counter = 0;
    }
  }
  return s_data;
}


/*---------------------------------------------------------------------------*/
// 2-hop additions
#include "contiki.h"
int16_t my_current_action_q = 0; // global variable for best parent Q-value

int16_t sarsa_get_my_q(void){
  return my_current_action_q;
}

void sarsa_save_neighbor_q(const uip_ipaddr_t *from_ip, int16_t received_q){
  rpl_nbr_t *nbr = rpl_neighbor_get_from_ipaddr((uip_ipaddr_t *)from_ip);
  if(nbr != NULL){
    sarsa_nbr_t *sarsa_data = get_sarsa_data(nbr);
    if(sarsa_data != NULL){
      sarsa_data->next_action_q = received_q;
    }
  }
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
static int32_t calculate_flink_quality(uint16_t raw_etx){
  if(raw_etx <= 128) return 100;
  else if(raw_etx >= 512) return 0;
  else {
    return  100 - (((raw_etx - 128) * 100) / 384);
  }
}
static int32_t
calculate_current_q(rpl_nbr_t *nbr, sarsa_nbr_t *data)
{
  if(nbr == NULL || data == NULL) return 0; 

  int32_t f_energy = (int32_t)data->energy_level;
  int32_t f_link_quality = calculate_flink_quality(nbr_link_metric(nbr));

  int32_t base_q = ((global_w_energy * f_energy) + (global_w_lq * f_link_quality)) / 100;

  int32_t rank_penalty = nbr->rank >> 3;

  return base_q - rank_penalty; 
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

  data->energy_level = nbr->mc.obj.energy.energy_est; // Update energy level with latest estimate from DIOs

  if(status == MAC_TX_OK) {
      data->learning_counter++;
      if(data->learning_counter < LEARNING_BATCH_SIZE) {
          return; // Skip the heavy math and go back to sleep!
      }
      data->learning_counter = 0; // Reset counter and proceed to math
  }
  
  /* 3. The True Environmental Reward */
  int32_t reward = 0;
  int32_t parent_battery = (int32_t)data->energy_level;

  if(status == MAC_TX_OK) {
          reward = parent_battery;  
          if(numtx > 1){
              reward -= (20*numtx);
          }
      
  } else {
      reward = -100; // Massive penalty for dropped packet
  }

  /* 4. Extract State Features */
  int32_t f_link_quality = calculate_flink_quality(nbr_link_metric(nbr));

  int32_t f_energy = parent_battery;

  int32_t current_q = calculate_current_q(nbr, data);

  /* 5. Future Value */
  int32_t future_value = (int32_t)data->next_action_q; // In SARSA, we use the Q-value of the action actually taken in the next state

  int32_t target;
  // If the neighbour is the root, we set the target to the immediate reward since there are no future states
  if(instance != NULL && nbr->rank == ROOT_RANK){
    target=reward;
  } else{
    target = reward + ((GAMMA * future_value) / 100); // div 100 for floating point math reasons
  }

  /* 6. Calculate True TD Error */
  int32_t td_error = target - current_q; 

  /* 7. Update Global Policy Weights */
  global_w_lq += ((ALPHA * td_error * f_link_quality) / 10000); 
  global_w_energy += ((ALPHA * td_error * f_energy) / 10000);

  // Weight clipping
  if (global_w_lq > MAX_WEIGHT) global_w_lq = MAX_WEIGHT;
  if (global_w_energy > MAX_WEIGHT) global_w_energy = MAX_WEIGHT;

  if(global_w_energy > MAX_WEIGHT) global_w_energy = MAX_WEIGHT;
  if(global_w_energy < MIN_WEIGHT) global_w_energy = MIN_WEIGHT;


  #ifdef SARSA_LOGGING
    uint16_t nbr_id = rpl_neighbor_get_lladdr(nbr)->u8[LINKADDR_SIZE - 1];
    
    // LOG 1: The SARSA Math (Proves the TD Error is correct)
    LOG_INFO("SARSA-MATH | Par: %d | curQ: %ld | rew: %ld | futQ: %ld | tgt: %ld | err: %ld\n",
             (int)nbr_id, (long)current_q, (long)reward, (long)future_value, (long)target, (long)td_error);

    // LOG 2: The Weight Update (Proves ALPHA is working)
    LOG_INFO("SARSA-WGHT | f_lq: %ld | f_eng: %ld | W_LQ: %ld | W_ENG: %ld\n",
             (long)f_link_quality, (long)f_energy, (long)global_w_lq, (long)global_w_energy);
  #endif
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

  if(d1 == NULL) return p1; 
  if(d2 == NULL) return p2;

  int32_t q1 = calculate_current_q(p1, d1);
  int32_t q2 = calculate_current_q(p2, d2);

  rpl_nbr_t *best;

  // +5 is a small bias to prevent Hysterisis
  if(p1 == curr_instance.dag.preferred_parent) {
      best = (q1 + SARSA_HYSTERESIS >= q2) ? p1 : p2; 
  }
  else if(p2 == curr_instance.dag.preferred_parent) {
      best = (q2 + SARSA_HYSTERESIS >= q1) ? p2 : p1;
  }
  else{
    best = (q1 > q2) ? p1 : p2;
  }

  // Save winning Q-value for DIO piggyback
  sarsa_nbr_t *best_data = get_sarsa_data(best);
  if(best_data != NULL){
    my_current_action_q = (int16_t)calculate_current_q(best, best_data);
  }

  #ifdef SARSA_LOGGING
    if(p1 != NULL && p2 != NULL) {
      uint16_t id1 = rpl_neighbor_get_lladdr(p1)->u8[LINKADDR_SIZE - 1];
      uint16_t id2 = rpl_neighbor_get_lladdr(p2)->u8[LINKADDR_SIZE - 1];
      uint16_t best_id = rpl_neighbor_get_lladdr(best)->u8[LINKADDR_SIZE - 1];
      
      LOG_INFO("EVALUATE: P1: %d (Q: %d) vs P2: %d (Q: %d) -> CHOSE: %d\n", 
               (int)id1, (int)q1, (int)id2, (int)q2, (int)best_id);
    }
  #endif

  return best;
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
#define LOG_CONF_LEVEL_DEFAULT LOG_LEVEL_WARN
//#define LOG_CONF_LEVEL_RPL LOG_LEVEL_INFO

/* =====================*/
/* MODIFIABLE DIRECTIVES*/
/* =====================*/

//SARSA
#define SARSA
#define SARSA_CONF_ALPHA 10
#define SARSA_CONF_GAMMA 80
//#define SARSA_LOGGING

//General
#define CONF_DRAIN_MAGNITUDE 500
#define CONF_COST_RX 0

/* =====================*/

/* Tell the node to use Objective Function 10 (SARSA) */
#ifdef SARSA
    #undef RPL_CONF_OF_OCP
    #define RPL_CONF_OF_OCP 10
    #define SARSA_ENABLED
#endif

#define RPL_CONF_WITH_MC 1

/* Turn on the Energy Tracker*/
#define ENERGEST_CONF_ON 1


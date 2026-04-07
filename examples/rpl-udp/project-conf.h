#define LOG_CONF_LEVEL_DEFAULT LOG_LEVEL_WARN
//#define LOG_CONF_LEVEL_RPL LOG_LEVEL_INFO

/* =====================*/
/* MODIFIABLE DIRECTIVES*/
/* =====================*/

//SARSA
//#define SARSA
#define SARSA_CONF_ALPHA 10
#define SARSA_CONF_GAMMA 80
#define SARSA_CONF_LEARNING_BATCH_SIZE 7

//Battery settings
#define CONF_DRAIN_MAGNITUDE 25
#define CONF_COST_RX 0
#define CONF_COST_TX 60
#define CONF_COST_CPU 20

/* =====================*/

/* Tell the node to use Objective Function 10 (SARSA) */
#ifdef SARSA
    #undef RPL_CONF_OF_OCP
    #define RPL_CONF_OF_OCP 10
    #define SARSA_ENABLED
    #define SARSA_LOGGING
#endif

#define RPL_CONF_WITH_MC 1

/* Turn on the Energy Tracker*/
#define ENERGEST_CONF_ON 1


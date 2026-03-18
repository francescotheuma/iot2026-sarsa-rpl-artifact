#define LOG_CONF_LEVEL_DEFAULT LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_INFO

#define SARSA

/* Tell the node to use Objective Function 10 (SARSA) */
#ifdef SARSA
    #undef RPL_CONF_OF_OCP
    #define RPL_CONF_OF_OCP 10
    #define SARSA_ENABLED
#endif

#define RPL_CONF_WITH_MC 1

/* Turn on the Energy Tracker*/
#define ENERGEST_CONF_ON 1


TIMEOUT(1800000); // Run for 1 hour of simulated time

log.writeFile("cooja.log","");

while (true) {
  if (msg) {
    // This writes every log line to a file named 'cooja.log' 
    // located in your contiki-ng/tools/cooja/build directory
    log.append("cooja.log", time + " " + "ID:" + id + " " + msg + "\n");
  }
  YIELD();
}
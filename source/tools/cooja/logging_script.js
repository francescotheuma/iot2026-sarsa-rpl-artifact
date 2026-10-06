TIMEOUT(900000); // Run for 1 hour of simulated time

let file="cooja_sarsa.log";

log.writeFile(file,"");

while (true) {
  if (msg) {
    // This writes every log line to a file named 'cooja.log' 
    // located in your contiki-ng/tools/cooja/build directory
    log.append(file, time + " " + "ID:" + id + " " + msg + "\n");
  }
  YIELD();
}
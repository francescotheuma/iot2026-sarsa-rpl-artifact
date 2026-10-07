TIMEOUT(900000); // Run for 15 minutes of simulated time

let file="cooja_sarsa.log";

log.writeFile(file,"");

while (true) {
  if (msg) {
    // Write each log line to file, relative to the Cooja working directory.
    log.append(file, time + " " + "ID:" + id + " " + msg + "\n");
  }
  YIELD();
}
TIMEOUT(1800000); // Run for 30 minutes of simulated time

log.writeFile("cooja.log","");

while (true) {
  if (msg) {
    // Write each log line to 'cooja.log', relative to the Cooja working directory.
    log.append("cooja.log", time + " " + "ID:" + id + " " + msg + "\n");
  }
  YIELD();
}
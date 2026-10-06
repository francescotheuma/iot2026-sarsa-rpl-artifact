TIMEOUT(1800000); // Run for 30 minutes total (1,800,000 ms)

let file = "cooja_sarsa.log";
log.writeFile(file, "");

let paused_once = false;
let pause_time = 900000000; // 15 minutes in microseconds

while (true) {
  // Check if we hit the 15-minute mark
  if (time >= pause_time && !paused_once) {
    log.append(file, time + " --- SIMULATION PAUSED: CHANGE DGRM LINKS NOW ---\n");
    mote.getSimulation().stopSimulation(); // Pauses the GUI
    paused_once = true;
  }

  if (msg) {
    // Write every log line
    log.append(file, time + " " + "ID:" + id + " " + msg + "\n");
  }
  
  YIELD();
}
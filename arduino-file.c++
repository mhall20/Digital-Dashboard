// Library - https://github.com/coryjfowler/MCP_CAN_lib/tree/master
#include <mcp_can.h>
#include <SPI.h>

/*

Find these:

VCC	5V
GND	GND
CS	10 (can be changed)
SO	12 (MISO)
SI	11 (MOSI)
SCK	13
INT	2

*/

// CS pin is which pin is the exact one for communication
const int SPI_CS_PIN = 10; // change based on what the pin is
MCP_CAN CAN(SPI_CS_PIN);

// Variables for CAN response handling - specific variables helped by AI
unsigned long canRequestTime = 0;
const unsigned long CAN_TIMEOUT = 1000;  // 1 second timeout for CAN response so Arduino doesn't get stuck
String pendingPID = "";
bool waitingForResponse = false;

void setup() {
  // Initialize serial communication at 115200 baud rate
  Serial.begin(115200);
  
  // Wait for serial connection to establish
  while (!Serial) {
    ;
  }
  
  // Initialize built in LED
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  
  // Initialized print
  Serial.println("Arduino Ready");

  // Initialize CAN communication at 500k - average speed for OBD2
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("CAN BUS Shield initialized");
  } else {
    Serial.println("CAN BUS Shield failed");
    while (1);
  }
  
  CAN.setMode(MCP_NORMAL);   // Set mode to normal - recommended
  pinMode(2, INPUT);         // Interrupt pin for CAN messages

}

void loop() {
  // Check if data is available to read
  if (Serial.available() > 0) {
    // Read the incoming string until newline
    String input = Serial.readStringUntil('\n');
    input.trim(); // Remove any whitespace
    
    // Process the command
    processCommand(input);
  }
  
  // Check for incoming CAN messages
  checkCANMessages();
  
  // Check if waiting for a response and timeout occurred
  if (waitingForResponse && (millis() - canRequestTime) > CAN_TIMEOUT) {
    Serial.println("No response - timeout");
    waitingForResponse = false;
  }
  
  // Add a small delay to prevent overwhelming the serial - adjust for later
  delay(10);
}

// Process commands from Python
void processCommand(String command) {
  // Convert to uppercase for case-insensitive comparison
  command.toUpperCase();
  
  if (command == "LED_ON") {
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.println("LED turned ON");
  } 
  else if (command == "LED_OFF") {
    digitalWrite(LED_BUILTIN, LOW);
    Serial.println("LED turned OFF");
  }
  else if (command == "PING") {
    Serial.println("PONG");
  }
  // Handle PID requests from Python (format: "01 0C" for PID 0C with mode 01)
  else if (command.length() >= 5) {
    // Try to parse as a PID request
    handlePIDRequest(command);
  }
  else if (command.length() > 0) {
    // Echo back any other text
    Serial.print("Echo: ");
    Serial.println(command);
  }
}

// Handle OBD2 PID requests - inputting from python
void handlePIDRequest(String command) {
  // Expected format: "01 0C" 
  int spaceIndex = command.indexOf(' ');
  
  if (spaceIndex == -1) {
    return; // Not a PID request
  }
  
  String mode = command.substring(0, spaceIndex);
  String pid = command.substring(spaceIndex + 1);
  
  // Validate hex format (both should be 2 hex chars)
  if (mode.length() != 2 || pid.length() != 2) {
    return;
  }
  
  // Send CAN request to vehicle with this mode/PID
  askCarPID(mode, pid);
}

// Request the car for a specific PID value
void askCarPID(String mode, String pid) {

  // Standard OBD2 request format:
  // - PID request goes to CAN ID 0x7DF (broadcast to all ECUs)
  // - Response comes from 0x7E8 (engine ECU)
  // - Byte 0: Length (2 = mode + PID)
  // - Byte 1: Mode (01 = show current data)
  // - Byte 2: PID
  
  byte modeHex = strtol(mode.c_str(), NULL, 16);
  byte pidHex = strtol(pid.c_str(), NULL, 16);
  
  // Prepare CAN message: length, mode, PID
  byte data[3] = {0x02, modeHex, pidHex};
  
  // Send request to vehicle (0x7DF is broadcast to all ECUs)
  if (CAN.sendMsgBuf(0x7DF, 0, 3, data) == CAN_OK) {

    // Set flag that we're waiting for a response
    waitingForResponse = true;
    canRequestTime = millis();
    pendingPID = pid;
  } else {
    Serial.println("CAN send failed");
  }
}

// Check for incoming CAN messages and process responses
void checkCANMessages() {
  unsigned long rxId;
  unsigned char len = 0;
  unsigned char rxBuf[8];
  
  // Check if data is available on CAN bus
  if (CAN_MSGAVAIL == CAN.checkReceive()) {
    // Read the message
    CAN.readMsgBuf(&rxId, &len, rxBuf);
    
    // Standard OBD2 response comes from 0x7E8 (engine ECU)
    // Response format:
    // - Byte 0: Response length
    // - Byte 1: Mode + 0x40 (e.g., 0x41 for mode 01)
    // - Byte 2: PID
    // - Bytes 3+: Data (A, B values)
    
    if (rxId == 0x7E8 && len >= 3) {
      byte responseMode = rxBuf[1];
      byte responsePID = rxBuf[2];
      
      // Check if this is the response we're waiting for
      if (waitingForResponse && responsePID == strtol(pendingPID.c_str(), NULL, 16)) {
        byte valueA = (len > 3) ? rxBuf[3] : 0;
        byte valueB = (len > 4) ? rxBuf[4] : 0;
        
        // Send formatted response to Python
        Serial.print("PID: ");
        Serial.print(valueA, HEX);
        if (valueB > 0 || pendingPID == "0C" || pendingPID == "1F") {
          Serial.print(" ");
          Serial.print(valueB, HEX);
        }
        Serial.print(" ");
        Serial.println(pendingPID);
        
        waitingForResponse = false;
      }
    }
  }
}


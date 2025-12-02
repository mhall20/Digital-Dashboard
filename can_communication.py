import serial
import serial.tools.list_ports
import threading
import sys
from datetime import datetime, timezone
from collections import deque
import pandas as pd
import numexpr

canCSV = "can.csv"
df = pd.read_csv(canCSV, index_col="pid")

def formula(pid, A, B=None):
    """ Take incoming PID command and return calculated value based on correlating formula """
    formula = df.at[pid, "formula"]
    # Some forumals have A and B but others only A
    if B is None:
        f = numexpr.evaluate(formula, local_dict={"A": A}).item()
    else:
        f = numexpr.evaluate(formula, local_dict={"A": A, "B": B}).item()

    return f"{f:.2f}{df.at[pid, 'unit']}"

def compute_value(pid, A, B=None):
    """ Compute numeric value and unit for pid """

    # Get units and formula
    unit = df.at[pid, 'unit']
    formula_str = df.at[pid, "formula"]

    if B is None:
        f = numexpr.evaluate(formula_str, local_dict={"A": A}).item()
    else:
        f = numexpr.evaluate(formula_str, local_dict={"A": A, "B": B}).item()
    return (float(f), unit)

def find_arduino_port():
    """ Find COM port of Arduino by scanning all available ports """
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if 'Arduino' in p.description or 'CH340' in p.description: # CH340 is common arduino clone
            return p.device
    return None

class SerialManager:
    """ Manage a serial connection with a background reader thread and a send() command """

    # baudrate and timeout and buffer is a default number
    def __init__(self, port, baudrate=115200, read_timeout=0.1, decode='utf-8', max_buffer=1000,
                 event_queue=None, event_callback=None):
        """ Create a SerialManager and use threading to read incoming lines in the background """

        # port settings
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.decode = decode

        # thread settings
        self._ser = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # internal buffer for incoming lines (thread-safe when used with _lock)
        self._buffer = deque(maxlen=max_buffer)

        self.event_queue = event_queue
        self.event_callback = event_callback # note to self: callback is leaving queue and coming back to last place

    def start(self):
        """ Start background thread by opening serial port """

        # if already running, skip
        if self._thread and self._thread.is_alive():
            return
        try:
            # connect to serial port
            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.read_timeout)
        except Exception as e:
            print(f"Failed to open {self.port}: {e}")
            raise

        # start thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self):
        """ Loop to read lines from serial """
        while not self._stop_event.is_set():
            try:
                # read line from serial port
                line = self._ser.readline()
                if not line:
                    continue
                try:
                    # decode line from bytes to string
                    decoded = line.decode(self.decode, errors='replace').strip()
                except Exception:
                    # show bytes if decoding fails
                    decoded = repr(line)

                # store message in internal buffer
                with self._lock:
                    self._buffer.append(decoded)

                # Right now this does not take into account PID with no forumla - might remove non-formula PIDs
                # Base 16 for int because OBD2 PIDs are hex
                if decoded.startswith('PID: '):
                    try:
                        parts = decoded[5:].split()  # Remove 'PID: ' and split into the bits

                        # split into A and B if B exists
                        if len(parts) == 2:
                            A, pid = parts
                            A = int(A, 16)
                            B = None
                        elif len(parts) == 3:
                            A, B, pid = parts
                            A = int(A, 16)
                            B = int(B, 16)
                        else:
                            # print invalid pid and skip it
                            print(f"Invalid PID format: {decoded}")
                            continue

                        # get command from dataframe
                        cmd = df.loc[pid, "command"]

                        # compute numeric value and unit
                        value, unit = compute_value(pid, A, B)
                        formatted = None
                        # create string formatted with value and unit - I don't think it will be used for the dashboard but will be good for debugging
                        if value is not None:
                            formatted = f"{value:.2f}{unit}"

                        # create event dict
                        event = {
                            "timestamp": datetime.now(timezone.utc).isoformat(), # might be needed for dashboard
                            "pid": pid,
                            "command": cmd,
                            "raw": {"A": A, "B": B},
                            "value": value, # main unit for dashboard
                            "unit": unit,
                            "formatted": formatted
                        }

                        # push to queue/callback if provided
                        if self.event_queue is not None:
                            try:
                                self.event_queue.put(event)
                            except Exception as e:
                                print(f"Failed to put event in queue: {e}")
                        if self.event_callback is not None:
                            try:
                                self.event_callback(event)
                            except Exception as e:
                                print(f"Event callback error: {e}")

                        # keep a debug print - turn off during non-testing
                        if formatted:
                            print(f"{cmd} -> {formatted}")
                        else:
                            print(f"{cmd} -> raw A={A} B={B}")
                    except Exception as e:
                        print(f"Error processing PID: {e}")
                else:
                    print(decoded)
            except Exception as e:
                print(f"Serial read error: {e}")
                break

    def send(self, message, newline=True):
        """ Send a message to the serial port - thread safe """

        # prepare message
        if isinstance(message, str):
            payload = message.encode(self.decode)
        else:
            payload = message
        # always add newline
        if newline and not payload.endswith(b"\n"):
            payload += b"\r\n"

        # send to serial port
        with self._lock:
            # check for serial port open
            if not self._ser or not self._ser.is_open:
                raise RuntimeError('Serial port not open')
            self._ser.write(payload)
            self._ser.flush() # ensure it gets sent

    def stop(self, wait=True):
        """ Stop thread and close serial port """
        self._stop_event.set()
        if wait and self._thread:
            self._thread.join(timeout=1.0) # wait for thread to end
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass

if __name__ == '__main__':

    port = find_arduino_port()
    if not port:
        print('No Arduino found')
        port = input('Enter COM port (e.g. COM3): ').strip() # Manual port entry if auto doesn't work

    # start serial manager
    mgr = SerialManager(port, 115200)
    try:
        mgr.start()
    except Exception as e:
        print('Could not start SerialManager:', e)
        sys.exit(1)

    # because of the thread, we can loop message sending without having to worry about reading from arduino
    try:
        while True:
            # give user ability to type commands
            try:
                s = input('> ')
            except EOFError:
                break
            if s is None:
                break

            # give user quit option
            cmd = s.strip()
            if cmd == '':
                continue
            if cmd == 'quit':
                break

            # otherwise send the text to the device
            try:
                mgr.send(s)
            except Exception as e:
                print('Send failed:', e)
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop()
        print('Stopped.')
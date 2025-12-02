import pygame
import math
import sys
import can_communication as can
import queue, threading, time, random
import pandas as pd

"""
translate to imperial units

when updating values, only update if there is a whole number change
"""

# -------------------- DRAWING FUNCTIONS --------------------

# maybe add ability to put logo instead of label text like for volt and fuel pressure or figure something out for that
def draw_gauge(center, radius, value, max_value, label):
    """ Create gauge with needle """

    # Draw outer circle
    pygame.draw.circle(screen, (255, 255, 255), center, radius, 3)

    # Draw tick marks - AI created
    for i in range(0, 181, 20):  # 0 to 180 degrees
        angle = math.radians(180 - i)
        x1 = center[0] + (radius - 15) * math.cos(angle)
        y1 = center[1] - (radius - 15) * math.sin(angle)
        x2 = center[0] + radius * math.cos(angle)
        y2 = center[1] - radius * math.sin(angle)
        pygame.draw.line(screen, (255, 255, 255), (x1, y1), (x2, y2), 2)

    # Draw needle - AI created
    angle = math.radians(180 - (value / max_value) * 180)
    x = center[0] + (radius - 30) * math.cos(angle)
    y = center[1] - (radius - 30) * math.sin(angle)
    pygame.draw.line(screen, (255, 0, 0), center, (x, y), 4)

    """
    # Draw value text
    font = pygame.font.SysFont(None, 40)
    text = font.render(f"{value:.0f}", True, (255, 255, 255))
    text_rect = text.get_rect(center=(center[0], center[1] + 50))
    screen.blit(text, text_rect)
    """

    # Draw label
    label_font = pygame.font.SysFont(None, 36)
    label_text = label_font.render(label, True, (200, 200, 200))
    label_rect = label_text.get_rect(center=(center[0], center[1] + radius - 20))
    screen.blit(label_text, label_rect)

# colors for status indicators
WHITE = (220, 220, 220)
GREEN = (0, 200, 0)
RED = (200, 0, 0)

def draw_text_centered(surface, text, font, y):
    """ Helper to draw centered text """
    t = font.render(text, True, (255, 255, 255))
    r = t.get_rect(center=(WIDTH // 2, y))
    surface.blit(t, r)

def draw_status_indicator(surface, x, y, label, state):
    """ Draw status indicator with label - for detection splash """
    color = WHITE if state is None else (GREEN if state else RED)
    pygame.draw.circle(surface, color, (x, y), 10)
    font = pygame.font.SysFont(None, 20)
    text = font.render(label, True, (255, 255, 255))
    surface.blit(text, (x + 16, y - 8))

# AI
def draw_box():
    """ Draw box that displays extra info """

    # draw a rounded-ish rectangle near the top center with current box info
    box_w, box_h = 420, 110
    x = (WIDTH - box_w) // 2
    y = 20
    # background
    pygame.draw.rect(screen, (30, 30, 30), (x, y, box_w, box_h), border_radius=8)
    # border
    pygame.draw.rect(screen, (100, 100, 100), (x, y, box_w, box_h), 2, border_radius=8)

    # get current option
    opt = box_options[box_index]
    pid = opt['pid']
    label = opt['label']

    # find value
    ev = last_values.get(pid)
    if ev:
        val_raw = ev.get('value')
        # Convert temperatures from Celsius to Fahrenheit for display
        if pid in ['05', '5C', '0F', '46']:  # Temperature PIDs
            val_raw = (val_raw * 9/5) + 32
            unit = '°F'
        else:
            unit = ev.get('unit', '')
        val = f"{val_raw:.1f}{unit}"
    else:
        val = 'N/A'

    # draw texts
    title_font = pygame.font.SysFont(None, 28)
    val_font = pygame.font.SysFont(None, 36)
    title = title_font.render(label, True, (220, 220, 220))
    val_surf = val_font.render(str(val), True, (255, 255, 255))

    # center title and value inside the box
    center_x = x + box_w // 2
    title_rect = title.get_rect(center=(center_x, y + 28))
    val_rect = val_surf.get_rect(center=(center_x, y + 64))
    screen.blit(title, title_rect)
    screen.blit(val_surf, val_rect)

    # hint for switching
    hint = title_font.render('Press SPACE to cycle', True, (120, 120, 120))
    hint_rect = hint.get_rect(center=(center_x, y + box_h + 16))
    screen.blit(hint, hint_rect)

def draw_status_panel():
    """ Draw initialization status panel """
    # top-left corner
    draw_status_indicator(screen, 20, 20, 'Arduino Detected', status['arduino_detected'])
    draw_status_indicator(screen, 20, 50, 'Serial Connected', status['serial_running'])
    draw_status_indicator(screen, 20, 80, 'Simulator Running', status['simulator_running'])

# -------------------- BOOTING FUNCTIONS --------------------

def boot():
    """ Final boot message for dashboard initialization """
    screen.fill((0, 0, 0))
    large_font = pygame.font.SysFont(None, 48)
    draw_text_centered(screen, 'Booting dashboard...', large_font, HEIGHT // 2 - 20)
    draw_status_panel()
    pygame.display.flip()
    time.sleep(1.2)

# -------------------- LOOP FUNCTIONS --------------------

# AI
def simulator(q, stop_event):
    """ Simulator that puts fake OBD2 events into queue """
    speed = 0
    rpm = 0
    # additional fake values for box options
    engine_time = 0.0  # seconds
    oil_temp = 85.0
    intake_temp = 30.0
    ambient_temp = 20.0
    while not stop_event.is_set():
        speed = (speed + random.randint(0, 3)) % 121
        rpm = (rpm + random.randint(10, 200)) % 8001
        ev_speed = {
            'timestamp': time.time(),
            'pid': '0D',
            'command': 'speed',
            'raw': {'A': int(speed) & 0xFF, 'B': None},
            'value': float(speed),
            'unit': 'kph',
            'formatted': f"{speed:.0f}kph",
        }
        ev_rpm = {
            'timestamp': time.time(),
            'pid': '0C',
            'command': 'rpm',
            'raw': {'A': (rpm >> 8) & 0xFF, 'B': rpm & 0xFF},
            'value': float(rpm),
            'unit': 'rpm',
            'formatted': f"{rpm:.0f}rpm",
        }
        try:
            q.put_nowait(ev_speed)
            q.put_nowait(ev_rpm)
            # update additional simulated sensors
            engine_time += 0.12
            # small random walk for temps
            oil_temp += random.uniform(-0.2, 0.5)
            intake_temp += random.uniform(-0.3, 0.3)
            ambient_temp += random.uniform(-0.1, 0.1)

            ev_engine = {
                'timestamp': time.time(),
                'pid': '1F',
                'command': 'engine_run_time',
                'raw': {'A': int(engine_time) >> 8 & 0xFF, 'B': int(engine_time) & 0xFF},
                'value': engine_time,
                'unit': 's',
                'formatted': f"{int(engine_time)}s",
            }
            ev_oil = {
                'timestamp': time.time(),
                'pid': '5C',
                'command': 'oil_temp',
                'raw': {'A': int(oil_temp + 40) & 0xFF, 'B': None},
                'value': oil_temp,
                'unit': '°C',
                'formatted': f"{oil_temp:.1f}°C",
            }
            ev_intake = {
                'timestamp': time.time(),
                'pid': '0F',
                'command': 'intake_air_temp',
                'raw': {'A': int(intake_temp + 40) & 0xFF, 'B': None},
                'value': intake_temp,
                'unit': '°C',
                'formatted': f"{intake_temp:.1f}°C",
            }
            ev_ambient = {
                'timestamp': time.time(),
                'pid': '46',
                'command': 'ambient_air_temp',
                'raw': {'A': int(ambient_temp + 40) & 0xFF, 'B': None},
                'value': ambient_temp,
                'unit': '°C',
                'formatted': f"{ambient_temp:.1f}°C",
            }
            # push them as well
            q.put_nowait(ev_engine)
            q.put_nowait(ev_oil)
            q.put_nowait(ev_intake)
            q.put_nowait(ev_ambient)
        except queue.Full:
            pass
        time.sleep(0.12)

def pid_poller(mgr, stop_event):
    """ Continuously request PIDs from the Arduino """

    # Open csv to get full list of chosen PIDs
    canCSV = "can.csv"
    df = pd.read_csv(canCSV, index_col="pid")
    pids_to_poll = [pid for pid in df.index if pd.notna(df.at[pid, "formula"]) and df.at[pid, "formula"] != ""]
    current_index = 0
    
    time.sleep(1)  # wait for arduino to be ready
    
    # test connection
    try:
        mgr.send("PING")
    except Exception:
        return
    
    last_request_time = time.time()
    poll_interval = 0.3  # seconds between requests - ai suggested
    
    # loop to send PID requests
    while not stop_event.is_set():
        current_time = time.time()
        
        # Send next PID request if enough time has passed
        if current_time - last_request_time >= poll_interval:
            if pids_to_poll:
                pid = pids_to_poll[current_index]
                try:
                    # Send in format: "01 <PID>" (mode 01 = current data)
                    mgr.send(f"01 {pid}")
                except Exception:
                    pass
                current_index = (current_index + 1) % len(pids_to_poll)
            last_request_time = current_time
        
        time.sleep(0.01)

# -------------------- SETUP --------------------

# initialize queue
event_queue = queue.Queue(maxsize=2000)

# status checks for initalization
status = {
    'arduino_detected': None,
    'serial_running': None,
    'simulator_running': None}

# check for arduino and serial connection
port = can.find_arduino_port()
mgr = None
poll_stop = threading.Event()  # stop poller event
poll_thread = None

if port:
    status['simulator_running'] = False
    status['arduino_detected'] = True
    # try to run and start serial manager
    try:
        mgr = can.SerialManager(port, event_queue=event_queue)
        mgr.start()
        status['serial_running'] = True
        # start polling thread
        poll_stop.clear()
        poll_thread = threading.Thread(target=pid_poller, args=(mgr, poll_stop), daemon=True)
        poll_thread.start()
    except Exception:
        status['serial_running'] = False
else:
    status['arduino_detected'] = None # set to none for simulation prompt later

# Pygame setup
pygame.init()
# increase window size to fit extra gauges
WIDTH, HEIGHT = 1200, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

# simulation controls
sim_stop = threading.Event() # stop simulator
sim_thread = None
prompt_for_test_mode = False
if status['arduino_detected'] is None:
    # no Arduino found; prompt user
    prompt_for_test_mode = True
    status['arduino_detected'] = False
    status['serial_running'] = False

# store last values for gauges
last_values = {}

# box options to cycle through with SPACE
# map user requested options to PIDs (1F engine run time, 5C oil temp, 0F intake air temp, 46 ambient air temp)
box_options = [
    {'label': 'Engine run time', 'pid': '1F'},
    {'label': 'Oil temp', 'pid': '5C'},
    {'label': 'Intake air temp', 'pid': '0F'},
    {'label': 'Ambient air temp', 'pid': '46'},
]
box_index = 0

# -------------------- MAIN LOOP --------------------

running = True
booted = False
while running:

    # key handling
    for event in pygame.event.get():

        # Basic quit handling
        if event.type == pygame.QUIT:
            running = False

        # if exc ever, quit out
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
            pygame.quit()
            sys.exit()

        # test mode prompt handling
        elif event.type == pygame.KEYDOWN and prompt_for_test_mode:

            # if Y, run simulator
            if event.key == pygame.K_y:
                status['simulator_running'] = True
                prompt_for_test_mode = False
                sim_stop.clear()
                sim_thread = threading.Thread(target=simulator, args=(event_queue, sim_stop), daemon=True)
                sim_thread.start()

            # if n, quit
            elif event.key == pygame.K_n:
                pygame.quit()
                sys.exit()

        # cycle box options on SPACE (only when not prompting)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not prompt_for_test_mode:
            box_index = (box_index + 1) % len(box_options)

    # draw UI
    screen.fill((0, 0, 0))
    draw_status_panel()

    # Prompt for simulator mode if needed
    if prompt_for_test_mode:
        font = pygame.font.SysFont(None, 28)
        draw_text_centered(screen, 'No Arduino found. Press Y to run test mode, N to quit.', font, HEIGHT // 3)

    # Final step: boot message
    if not booted and (status['serial_running'] or status['simulator_running']):
        boot()
        booted = True

    # take incoming events from queue
    while True:
        try:
            ev = event_queue.get_nowait() # get return item without blocking
        except queue.Empty:
            break
        # store last value per pid
        last_values[ev['pid']] = ev

    if booted and (status['simulator_running'] or status['serial_running']): # show gauges in test mode OR regular mode
        # clear splash screen before gauges
        screen.fill((0, 0, 0))

        # draw info box
        draw_box()

        # small gauges positions
        oil_pos = (int(WIDTH * 0.12), int(HEIGHT * 0.25))      # top-left
        fuel_pos = (int(WIDTH * 0.12), int(HEIGHT * 0.75))     # bottom-left
        volt_pos = (int(WIDTH * 0.88), int(HEIGHT * 0.25))     # top-right
        coolant_pos = (int(WIDTH * 0.88), int(HEIGHT * 0.75))  # bottom-right

        # main gauges positions
        left_main = (int(WIDTH * 0.33), int(HEIGHT * 0.55))
        right_main = (int(WIDTH * 0.67), int(HEIGHT * 0.55))

        # read values (fall back to sensible defaults)
        oil_val = last_values.get('0A', {}).get('value', 15)
        fuel_val = last_values.get('2F', {}).get('value', 60)
        volt_val = last_values.get('33', {}).get('value', 12)
        coolant_val_c = last_values.get('05', {}).get('value', 20)
        
        # Convert coolant temp from Celsius to Fahrenheit
        coolant_val = (coolant_val_c * 9/5) + 32

        # draw small gauges (radius 70)
        draw_gauge(oil_pos, 70, oil_val, 100, 'PSI')
        draw_gauge(fuel_pos, 70, fuel_val, 100, '%')
        draw_gauge(volt_pos, 70, volt_val, 16, 'Volts')
        draw_gauge(coolant_pos, 70, coolant_val, 250, '°F')

        # draw main gauges (radius 180)
        speed_val_kph = last_values.get('0D', {}).get('value', 0)
        speed_val = speed_val_kph * 0.621371  # Convert KM/H to MPH
        rpm_val = last_values.get('0C', {}).get('value', 0)
        draw_gauge(left_main, 180, speed_val, 125, 'MPH')
        draw_gauge(right_main, 180, rpm_val, 8000, 'RPM')

    pygame.display.flip()
    clock.tick(30)

# -------------------- POST GAME --------------------

# cleanup after loop
if sim_thread and sim_thread.is_alive():
    sim_stop.set()
    sim_thread.join(timeout=1.0)
if poll_thread and poll_thread.is_alive():
    poll_stop.set()
    poll_thread.join(timeout=1.0)
if mgr:
    try:
        mgr.stop()
    except Exception:
        pass

# quit game
pygame.quit()
sys.exit()
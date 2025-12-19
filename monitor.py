import argparse
import asyncio
import base64
import contextlib
import csv
from datetime import datetime
from email.mime.text import MIMEText
import os
from pathlib import Path
import signal
import time

from bleak import BleakScanner

# Gmail API imports - will be conditionally used if credentials are available
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pyacaia import AcaiaScale

from simulator import create_mock_scale


def get_state_file_path():
    """Get the path to the state file using XDG_STATE_HOME."""
    xdg_state_home = os.getenv("XDG_STATE_HOME")
    if xdg_state_home:
        state_dir = Path(xdg_state_home) / "acaia-scale"
    else:
        state_dir = Path.home() / ".local" / "state" / "acaia-scale"

    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "mac_address.txt"


def load_mac_address():
    """Load MAC address from state file."""
    state_file = get_state_file_path()
    if state_file.exists():
        return state_file.read_text().strip()
    return None


def save_mac_address(mac):
    """Save MAC address to state file."""
    state_file = get_state_file_path()
    state_file.write_text(mac)


def get_gmail_credentials():
    """Get Gmail API credentials from credentials.json and token.json."""
    # Gmail API scopes for sending emails
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']

    # Look for credentials in project directory or ~/.config/acaia-scale/
    credentials_locations = [
        Path('credentials.json'),
        Path.home() / '.config' / 'acaia-scale' / 'credentials.json'
    ]

    credentials_file = None
    for location in credentials_locations:
        if location.exists():
            credentials_file = location
            break

    if not credentials_file:
        return None

    # Token file stored in same directory as credentials
    token_file = credentials_file.parent / 'token.json'

    creds = None
    # Load token if it exists
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        token_file.write_text(creds.to_json())

    return creds


def send_battery_alert(battery_level, threshold, recipient_email, mac_address=None):
    """Send battery alert email via Gmail API.

    Args:
        battery_level: Current battery percentage
        threshold: Battery threshold that triggered alert
        recipient_email: Email address to send alert to
        mac_address: Scale MAC address (optional)

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        creds = get_gmail_credentials()
        if not creds:
            print("Warning: Gmail credentials not found. Skipping email alert.")
            print("To enable email alerts, set up credentials.json (see documentation)")
            return False

        # Build Gmail service
        service = build('gmail', 'v1', credentials=creds)

        # Create email message
        subject = "Low Battery Alert: Acaia Scale"
        body = f"""Battery Alert for Acaia Scale

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Battery Level: {battery_level:.1f}%
Alert Threshold: {threshold:.1f}%
"""
        if mac_address:
            body += f"Scale MAC Address: {mac_address}\n"

        body += """
This is an automated alert from your Acaia scale monitoring system.
Please charge or replace the battery soon to avoid monitoring interruption.
"""

        message = MIMEText(body)
        message['to'] = recipient_email
        message['subject'] = subject

        # Encode message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        # Send email
        service.users().messages().send(userId="me", body=create_message).execute()
        print(f"Battery alert email sent to {recipient_email}")
        return True

    except HttpError as error:
        print(f"Error sending battery alert email: {error}")
        return False
    except Exception as e:
        print(f"Unexpected error sending battery alert: {e}")
        return False


async def discover_acaia_scale():
    """Discover Acaia scale via Bluetooth LE."""
    print("Scanning for Acaia scales...")
    devices = await BleakScanner.discover(timeout=10.0)

    acaia_devices = []
    for device in devices:
        name = device.name or "Unknown"
        if any(keyword in name.upper() for keyword in ["PROCH", "PR BT", "ACAIA", "PYXIS", "LUNAR", "PEARL"]):
            acaia_devices.append(device)
            print(f"Found Acaia device: {device.address} - {name}")

    if not acaia_devices:
        raise RuntimeError("No Acaia devices found. Make sure your scale is on and in pairing mode.")

    if len(acaia_devices) > 1:
        print("\nMultiple Acaia devices found:")
        for i, device in enumerate(acaia_devices, 1):
            print(f"  {i}. {device.address} - {device.name}")
        choice = int(input("Select device number: ")) - 1
        return acaia_devices[choice].address

    return acaia_devices[0].address


async def connect_scale(use_simulator, scenario, mac_address):
    """Connect to scale (simulator or real hardware)."""
    if use_simulator:
        scale = create_mock_scale(scenario=scenario)
        scale.connect()
        return scale
    else:
        scale = AcaiaScale(mac=mac_address)
        scale.connect()
        return scale


async def monitor_scale(scale, log_file, shutdown_event, use_simulator=False, scenario="random", mac_address=None, interval=1.0, min_bird_weight=25, max_bird_weight=60, battery_threshold=20.0, battery_check_interval=300, alert_email=None, disable_battery_alerts=False):
    """Monitor scale continuously and log bird weights."""
    bird_start_time = None
    last_battery_check = 0
    battery_alert_sent = False
    battery_monitoring_disabled = False

    # Initialize CSV file
    csv_file = open(log_file, 'a', newline='') # noqa: SIM115
    csv_writer = csv.writer(csv_file)

    # Write header if file is new
    if csv_file.tell() == 0:
        csv_writer.writerow(['timestamp', 'weight_g', 'event', 'battery_pct'])
        csv_file.flush()

    print(f"Monitoring scale (logging to {log_file})...")
    print(f"Bird weight range: {min_bird_weight}-{max_bird_weight}g")
    print("Press Ctrl+C to stop\n")

    try:
        while not shutdown_event.is_set():
            # Check battery level periodically
            current_time = time.time()
            battery_level = None
            if not battery_monitoring_disabled and (current_time - last_battery_check) >= battery_check_interval:
                try:
                    battery_level = scale.battery
                    if battery_level is not None:
                        last_battery_check = current_time
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Battery: {battery_level:.1f}%")

                        # Check if battery is below threshold
                        if battery_level <= battery_threshold and not battery_alert_sent:
                            if alert_email and not disable_battery_alerts:
                                if send_battery_alert(battery_level, battery_threshold, alert_email, mac_address):
                                    battery_alert_sent = True
                            else:
                                print(f"Warning: Battery low ({battery_level:.1f}%) but no alert email configured")
                                battery_alert_sent = True

                        # Reset alert flag if battery goes above threshold + 5% (hysteresis)
                        elif battery_level > (battery_threshold + 5.0):
                            battery_alert_sent = False
                except AttributeError:
                    if not battery_monitoring_disabled:
                        print("Warning: scale.battery not available. Battery monitoring disabled.")
                        battery_monitoring_disabled = True
                except Exception as e:
                    print(f"Warning: Error reading battery level: {e}")

            # Check if the scale is still connected, perhaps it was turned off?
            if not scale.connected:
                print("\nScale disconnected, attempting to reconnect...")

                # Try to disconnect cleanly if possible
                with contextlib.suppress(Exception):
                    scale.disconnect()

                # Retry connection with exponential backoff
                retry_delay = 1
                max_retry_delay = 30
                while not shutdown_event.is_set():
                    try:
                        scale = await connect_scale(use_simulator, scenario, mac_address)
                        print("Reconnected successfully!")
                        # Reset bird state after reconnection
                        bird_start_time = None
                        # Reset battery check timer but keep alert state
                        last_battery_check = 0
                        break
                    except Exception as e:
                        print(f"Reconnection failed: {e}. Retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, max_retry_delay)

                # If we exited due to shutdown, break outer loop
                if shutdown_event.is_set():
                    break

                # Give scale a moment to stabilize after reconnection
                await asyncio.sleep(1)
                continue

            weight = scale.weight or 0.0
            timestamp = datetime.now().isoformat()

            # Auto-tare logic: tare if weight is non-zero but outside bird range
            if weight != 0 and (weight < min_bird_weight or weight > max_bird_weight):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-taring (weight: {weight:.1f}g)")
                scale.tare()
                time.sleep(0.5)  # Give scale time to process tare
                continue

            # Detect bird landing
            if bird_start_time is None and min_bird_weight <= weight <= max_bird_weight:
                bird_start_time = datetime.now()
                event = "bird_landed"
                print(f"[{bird_start_time.strftime('%H:%M:%S')}] Bird landed: {weight:.1f}g")
                csv_writer.writerow([timestamp, f"{weight:.2f}", event, battery_level if battery_level is not None else ""])
                csv_file.flush()

            # Log while bird is present
            elif bird_start_time is not None and min_bird_weight <= weight <= max_bird_weight:
                event = "bird_present"
                csv_writer.writerow([timestamp, f"{weight:.2f}", event, battery_level if battery_level is not None else ""])
                csv_file.flush()

            # Detect bird leaving
            elif bird_start_time is not None and weight < min_bird_weight:
                duration = (datetime.now() - bird_start_time).total_seconds()
                bird_start_time = None
                event = "bird_left"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Bird left (duration: {duration:.1f}s)")
                csv_writer.writerow([timestamp, f"{weight:.2f}", event, battery_level if battery_level is not None else ""])
                csv_file.flush()

            await asyncio.sleep(interval)

    finally:
        print("\nMonitoring stopped")
        csv_file.close()
        scale.disconnect()


async def main():
    parser = argparse.ArgumentParser(description="Monitor Acaia scale for bird weights")
    parser.add_argument("--discover", action="store_true", help="Force rediscovery of the scale")
    parser.add_argument("--simulate", action="store_true", help="Use simulator instead of real hardware")
    parser.add_argument("--scenario", default="random",
                        choices=["random", "quick_visits", "long_visit", "frequent_tare"],
                        help="Simulation scenario (only with --simulate)")
    parser.add_argument("--log-file", default="bird_weights.csv", help="CSV file to log weights (default: bird_weights.csv)")
    parser.add_argument("--interval", type=float, default=1.5, help="Polling interval in seconds (default: %(default)s)")
    parser.add_argument("--min-weight", type=float, default=20.0, help="Minimum bird weight in grams (default: 20)")
    parser.add_argument("--max-weight", type=float, default=60.0, help="Maximum bird weight in grams (default: 60)")
    parser.add_argument("--battery-threshold", type=float, default=20.0, help="Battery percentage threshold for alerts (default: 20)")
    parser.add_argument("--battery-check-interval", type=int, default=300, help="Battery check interval in seconds (default: 300 = 5 min)")
    parser.add_argument("--alert-email", type=str, help="Email address to receive battery alerts (overrides ALERT_EMAIL env var)")
    parser.add_argument("--disable-battery-alerts", action="store_true", help="Disable battery email alerts")
    args = parser.parse_args()

    # logging.basicConfig(level=logging.DEBUG)
    # logging.getLogger('pygatt').setLevel(logging.DEBUG)

    # Get alert email from command line or environment variable
    alert_email = args.alert_email or os.getenv('ALERT_EMAIL')

    # Check Gmail OAuth credentials at startup if email alerts are enabled
    if alert_email and not args.disable_battery_alerts:
        print("Checking Gmail OAuth credentials for email alerts...")
        creds = get_gmail_credentials()
        if not creds:
            print("\nERROR: Gmail credentials not found.")
            print("Email alerts require OAuth authentication with Gmail.")
            print("\nTo set up email alerts:")
            print("  1. Create a Google Cloud project and enable Gmail API")
            print("  2. Download OAuth credentials as credentials.json")
            print("  3. Place credentials.json in:")
            print("     - Current directory, OR")
            print("     - ~/.config/acaia-scale/credentials.json")
            print("\nRun the program again to complete OAuth flow.")
            print("\nAlternatively, use --disable-battery-alerts to skip email alerts.")
            return
        print("Gmail OAuth credentials verified successfully!")

    # Create shutdown event for clean SIGINT handling
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown_event.set)

    # Use simulator or real hardware
    mac = None
    if args.simulate:
        print(f"Using simulator with scenario: {args.scenario}")
        scale = await connect_scale(args.simulate, args.scenario, None)
    else:
        # Get MAC address
        if not args.discover:
            mac = load_mac_address()

        if mac is None or args.discover:
            mac = await discover_acaia_scale()
            save_mac_address(mac)
            print(f"Saved MAC address: {mac}")
        else:
            print(f"Using cached MAC address: {mac}")

        # Connect to scale
        print(f"Connecting to Acaia scale at {mac}...")
        scale = await connect_scale(args.simulate, args.scenario, mac)
        print("Connected!")

    # Start monitoring
    await monitor_scale(
        scale,
        args.log_file,
        shutdown_event,
        use_simulator=args.simulate,
        scenario=args.scenario,
        mac_address=mac,
        interval=args.interval,
        min_bird_weight=args.min_weight,
        max_bird_weight=args.max_weight,
        battery_threshold=args.battery_threshold,
        battery_check_interval=args.battery_check_interval,
        alert_email=alert_email,
        disable_battery_alerts=args.disable_battery_alerts
    )


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()

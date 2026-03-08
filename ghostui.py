#!/usr/bin/python3

import configparser
import os
import pwd
import shutil
import sys
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired, run

try:
    import npyscreen
    import requests
    from rich import print
except ModuleNotFoundError as exc:
    sys.stderr.write(
        f"Missing dependency: {exc.name}\n"
        "Install requirements into the Python interpreter you are using.\n"
        "If you are in a virtualenv, run `python3 ghostui.py` instead of `sudo python3 ghostui.py`.\n"
    )
    sys.exit(1)

CYBERGHOST_BINARY = shutil.which("cyberghostvpn")
SUDO_BINARY = shutil.which("sudo")
IP_INFO_URL = "http://ip-api.com/json"
REQUEST_TIMEOUT = 10
COMMAND_TIMEOUT = 45


class GhostUIError(RuntimeError):
    pass


def ensure_environment():
    if not CYBERGHOST_BINARY:
        raise GhostUIError("CyberGhostVPN seems not installed on this system.")
    if os.getuid() != 0 and not SUDO_BINARY:
        raise GhostUIError("sudo is required when running GhostVPN without root.")


def ensure_sudo_session():
    if os.getuid() == 0:
        return

    try:
        run([SUDO_BINARY, "-v"], check=True, timeout=COMMAND_TIMEOUT)
    except FileNotFoundError as exc:
        raise GhostUIError("sudo could not be found on this system.") from exc
    except TimeoutExpired as exc:
        raise GhostUIError("sudo authentication timed out.") from exc
    except CalledProcessError as exc:
        raise GhostUIError("sudo authentication failed.") from exc


def build_cyberghost_command(*args):
    command = [CYBERGHOST_BINARY, *args]
    if os.getuid() != 0:
        return [SUDO_BINARY, "-n", *command]
    return command


def run_cyberghost_command(*args, timeout=COMMAND_TIMEOUT):
    try:
        completed = run(
            build_cyberghost_command(*args),
            capture_output=True,
            check=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GhostUIError("CyberGhostVPN binary could not be found.") from exc
    except TimeoutExpired as exc:
        raise GhostUIError("CyberGhostVPN command timed out.") from exc
    except CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise GhostUIError(output or "CyberGhostVPN command failed.") from exc

    return completed.stdout


def get_country_list():
    outp = run_cyberghost_command("--country-code")
    countries = {}
    # outp is something like
    # +-----+----------------------+--------------+
    # | No. |     Country Name     | Country Code |
    # +-----+----------------------+--------------+
    # |  1  |       Andorra        |      AD      |
    # | ... |         ...          |      ...     |
    # | 100 |     South Africa     |      ZA      |
    # +-----+----------------------+--------------+
    for line in outp.splitlines():
        columns = line.split("|")
        if len(columns) != 5 or columns[0] or columns[-1]:
            continue

        number = columns[1].strip()
        country = columns[2].strip()
        code = columns[3].strip()
        if (
            number.isnumeric()
            and country.isascii()
            and code.isalpha()
            and len(code) == 2
            and code.isupper()
        ):
            countries[country] = code

    if not countries:
        raise GhostUIError("Country list could not be loaded from CyberGhostVPN.")

    return dict(sorted(countries.items()))


def fetch_ip_info():
    try:
        response = requests.get(IP_INFO_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        api_data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GhostUIError("IP information could not be retrieved.") from exc

    return {
        "query": api_data.get("query", "Unknown"),
        "country": api_data.get("country", "Unknown"),
        "regionName": api_data.get("regionName", "Unknown"),
        "isp": api_data.get("isp", "Unknown"),
    }


def get_auth_config_path():
    sudo_user = os.getenv("SUDO_USER")
    if sudo_user:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir) / ".cyberghost" / "config.ini"
        except KeyError:
            pass

    pkexec_uid = os.getenv("PKEXEC_UID")
    if pkexec_uid and pkexec_uid.isdigit():
        try:
            return Path(pwd.getpwuid(int(pkexec_uid)).pw_dir) / ".cyberghost" / "config.ini"
        except KeyError:
            pass

    return Path.home() / ".cyberghost" / "config.ini"


def show_error(message):
    npyscreen.notify_confirm(message, "ERROR")


def show_ip_info():
    api_data = fetch_ip_info()
    npyscreen.notify_confirm(
        (
            f"IP Address: {api_data['query']}\n"
            f"Country: {api_data['country']}\n"
            f"Region: {api_data['regionName']}\n"
            f"ISP: {api_data['isp']}"
        ),
        "NOTIFICATION",
    )


vpn_country = {}


# Class for main form that handles connections and country selections
class MainForm(npyscreen.FormBaseNew):
    def create(self):
        # Terminal resolution
        self.y, self.x = self.useable_space()

        # Parsing countries
        self.get_country = self.add(
            npyscreen.TitleCombo, name="Select Country:",
            values=[cont for cont in vpn_country]
        )

        # --------------- BUTTONS ------------
        self.add(
            npyscreen.ButtonPress, name="Connect",
            when_pressed_function=self.make_connection, relx=20,
            rely=15
        )
        self.add(
            npyscreen.ButtonPress, name="Stop Connection",
            when_pressed_function=self.stop_connection, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Auth Information",
            when_pressed_function=self.auth_info, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Get IP Info",
            when_pressed_function=self.get_ip_info, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Quit",
            when_pressed_function=self.exit_button, relx=20,
            rely=20
        )

    # ------------------- ACTIONS -------------
    def exit_button(self):
        # Ask user for exit
        exiting = npyscreen.notify_yes_no(
            "Are you sure to quit?", "WARNING", editw=2
        )
        if exiting:
            self.parentApp.setNextForm(None)
            sys.exit(0)

    def make_connection(self):
        if self.get_country.value is None:
            show_error("Select a country before connecting.")
            return

        target_country = str(self.get_country.values[self.get_country.value]).strip()
        try:
            npyscreen.notify_wait(
                f"Connecting to: {target_country}", "PROGRESS"
            )
            run_cyberghost_command(
                "--connect", "--country-code", vpn_country[target_country]
            )
            npyscreen.notify_wait(
                "Requesting IP information please wait...", "PROGRESS"
            )
            show_ip_info()
        except GhostUIError as exc:
            show_error(str(exc))

    def stop_connection(self):
        stops = npyscreen.notify_yes_no(
            "Are you sure to stop VPN connection?", "WARNING",
            editw=2
        )
        if not stops:
            return

        try:
            npyscreen.notify_wait(
                "Disabling VPN connection please wait...", "PROGRESS"
            )
            run_cyberghost_command("--stop")
            npyscreen.notify_confirm(
                "Your VPN connection has been stopped.", "NOTIFICATION"
            )
        except GhostUIError as exc:
            show_error(str(exc))

    def auth_info(self):
        auth_conf = configparser.ConfigParser()
        config_path = get_auth_config_path()
        if not config_path.exists():
            show_error(f"Config file not found: {config_path}")
            return

        auth_conf.read(config_path)
        if "account" not in auth_conf or "username" not in auth_conf["account"]:
            show_error("Account information could not be read from config.")
            return

        npyscreen.notify_confirm(
            f"User: {auth_conf['account']['username']}",
            "INFO"
        )

    def get_ip_info(self):
        try:
            npyscreen.notify_wait(
                "Requesting IP information please wait...", "PROGRESS"
            )
            show_ip_info()
        except GhostUIError as exc:
            show_error(str(exc))


# Class for main application
class MainApp(npyscreen.NPSAppManaged):
    # When app starts
    def onStart(self):
        npyscreen.setTheme(npyscreen.Themes.ColorfulTheme)

        # Our main application
        self.addForm(
            "MAIN", MainForm, name="CyberGhostVPN TUI v0.2", lines=30, columns=90
        )

# Execution area
def main():
    try:
        global vpn_country
        ensure_environment()
        ensure_sudo_session()
        vpn_country = get_country_list()
        app = MainApp()
        app.run()
    except GhostUIError as exc:
        print(f"[bold white on red]{exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("[+] Goodbye...")
        sys.exit(0)


if __name__ == '__main__':
    main()

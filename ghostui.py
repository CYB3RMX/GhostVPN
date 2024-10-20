#!/usr/bin/python3

import os
import sys
import requests
import npyscreen
import configparser
from rich import print
from subprocess import Popen, PIPE, check_output

# Checking permissions
if int(os.getuid()) != 0:
    print("[bold white on red]You need root permissions to use this tool!!")
    sys.exit(1)

# Checking CyberGhostVPN existence
if os.path.exists("/usr/bin/cyberghostvpn") is False:
    print("[bold white on red]CyberGhostVPN seems not installed on this system!!")
    sys.exit(1)

# Available countries
def get_country_list():
    get_countr = ["cyberghostvpn", "--country-code"]
    outp = check_output(get_countr, text=True)
    # outp is something like
    # +-----+----------------------+--------------+
    # | No. |     Country Name     | Country Code |
    # +-----+----------------------+--------------+
    # |  1  |       Andorra        |      AD      |
    # | ... |         ...          |      ...     |
    # | 100 |     South Africa     |      ZA      |
    # +-----+----------------------+--------------+
    return {
            country: code
            for line in outp.split(os.linesep)
            # We check that line is of the form
            # '|  33 |        France        |      FR      |'
            if (len(c:=line.split("|")) == 5)
            and not (c[0] or c[-1])
            and (num:=c[1].strip()).isnumeric()
            and (country:=c[2].strip()).isascii()
            and (code:=c[3].strip()).isalpha()
            and len(code) == 2
            and code.isupper()
        }
# vpn_country = {"Andorra": "AD", ..., "South Africa": "ZA"}
vpn_country = get_country_list()


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
            when_pressed_function=self.MakeConnection, relx=20,
            rely=15
        )
        self.add(
            npyscreen.ButtonPress, name="Stop Connection",
            when_pressed_function=self.StopConnect, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Auth Information",
            when_pressed_function=self.AuthInfo, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Get IP Info",
            when_pressed_function=self.GetIPInfo, relx=20
        )
        self.add(
            npyscreen.ButtonPress, name="Quit",
            when_pressed_function=self.ExitButton, relx=20,
            rely=20
        )

    # ------------------- ACTIONS -------------
    def ExitButton(self):
        # Ask user for exit
        exiting = npyscreen.notify_yes_no(
            "Are you sure to quit?", "WARNING", editw=2
        )
        if exiting:
            self.parentApp.setNextForm(None)
            sys.exit(0)
        else:
            pass
    def MakeConnection(self):
        try:
            target_country = str(self.get_country.values[self.get_country.value].replace('\n', ''))
            npyscreen.notify_wait(
                f"Connecting to: {target_country}", "PROGRESS"
            )
            make_conn = ["cyberghostvpn", "--connect", "--country-code", f"{vpn_country[target_country]}"]
            comm = Popen(make_conn, stderr=PIPE, stdout=PIPE)
            comm.wait()
            npyscreen.notify_wait(
                "Requesting IP information please wait...", "PROGRESS"
            )
            ip_info = requests.get("http://ip-api.com/json")
            api_data = ip_info.json()
            npyscreen.notify_confirm(
                f"IP Address: {api_data['query']}\nCountry: {api_data['country']}\nRegion: {api_data['regionName']}\nISP: {api_data['isp']}",
                "NOTIFICATION"
            )
        except:
            pass
    def StopConnect(self):
        try:
            stops = npyscreen.notify_yes_no(
                "Are you sure to stop VPN connection?", "WARNING",
                editw=2
            )
            if stops:
                npyscreen.notify_wait(
                    "Disabling VPN connection please wait...", "PROGRESS"
                )
                stop_conn = ["cyberghostvpn", "--stop"]
                comm = Popen(stop_conn, stderr=PIPE, stdout=PIPE)
                comm.wait()
                npyscreen.notify_confirm(
                    "Your VPN connection has been stopped.", "NOTIFICATION"
                )
            else:
                pass
        except:
            pass
    def AuthInfo(self):
        auth_conf = configparser.ConfigParser()
        username = os.getenv("SUDO_USER")
        auth_conf.read(f"/home/{username}/.cyberghost/config.ini")
        npyscreen.notify_confirm(
            f"User: {auth_conf['account']['username']}",
            "INFO"
        )
    
    def GetIPInfo(self):
        try:
            npyscreen.notify_wait(
                "Requesting IP information please wait...", "PROGRESS"
            )
            ip_info = requests.get("http://ip-api.com/json")
            api_data = ip_info.json()
            npyscreen.notify_confirm(
                f"IP Address: {api_data['query']}\nCountry: {api_data['country']}\nRegion: {api_data['regionName']}\nISP: {api_data['isp']}",
                "NOTIFICATION"
            )
        except:
            pass

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
if __name__ == '__main__':
    try:
        app = MainApp()
        app.run()
    except KeyboardInterrupt:
        print("[+] Goodbye...")
        sys.exit(0)

#!/opt/homebrew/bin/python3.11
# Copyright 2024 by moshix
# A telnet based server to search TEXT documents
# v0.1    humble beginnings
# v0.11   make it handle whole lines at a time
# v0.2    some commands /search 
# v0.3    make it indepedent of capitalization
# v0.4    handl SIGINT (sorta)
# v0.5    tabulate
# v0.6    /stats
# v0.7    /uptime
# v0.8    Make it an SSh server
# v0.9    Handle PTY
# v0.91   Handle shell
# 0.93    Handle client typing better
import socket
import threading
import os
import signal
import time
import paramiko
from datetime import datetime
from paramiko import RSAKey, ServerInterface, AUTH_SUCCESSFUL, OPEN_SUCCEEDED

# Version information
version = "1.0"

# ANSI color codes for formatting
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[1;32m"
COLOR_BLUE = "\033[1;34m"
COLOR_RED = "\033[1;31m"
COLOR_YELLOW = "\033[1;33m"

FILES_DIR = "FILES/"
VIDEOS_FILE = "videos.txt"

class SSHServerInterface(ServerInterface):
    def check_auth_password(self, username, password):
        # Allow any username and password for simplicity
        return AUTH_SUCCESSFUL

    def check_channel_request(self, kind, chanid):
        # Only allow 'session' channels
        if kind == 'session':
            return OPEN_SUCCEEDED
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        # Always accept shell requests
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        # Always accept PTY requests
        return True

class SSHServer:
    def __init__(self, host='0.0.0.0', port=8023):
        self.host = host
        self.port = port

        # Initialize server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"SSH server started on {self.host}:{self.port}")

        # Load server key for SSH
        self.server_key = RSAKey(filename='server_key')

        # Initialize statistics and state variables
        self.client_count = 0
        self.total_clients = 0
        self.total_messages = 0
        self.search_count = 0
        self.videosearch_count = 0
        self.total_commands = 0
        self.start_time = time.time()
        self.start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lock = threading.Lock()
        self.running = True

        # Handle SIGINT (Control-C) to shut down the server gracefully
        signal.signal(signal.SIGINT, self.handle_sigint)

    def handle_sigint(self, signum, frame):
        print("\nSIGINT received. Shutting down the server.")
        self.running = False
        self.server_socket.close()

    def handle_client(self, client_socket, client_address):
        transport = paramiko.Transport(client_socket)
        transport.add_server_key(self.server_key)
        server = SSHServerInterface()

        try:
            transport.start_server(server=server)
            chan = transport.accept(20)  # Wait up to 20 seconds for a channel
            if chan is None:
                print(f"Client {client_address} did not request a channel.")
                return

            # Handle PTY and shell requests
            chan.get_pty()
            chan.invoke_shell()

            # Increment client count
            with self.lock:
                self.client_count += 1
                self.total_clients += 1
            print(f"Accepted connection from {client_address}")

            try:
                # Clear the screen for the client
                clear_screen = "\n" * 25
                chan.send(clear_screen.encode('utf-8'))

                # Send welcome, version, and help messages to the client
                welcome_message = f"{COLOR_GREEN}Welcome to the SSH server! Version: {version}{COLOR_RESET}\r\n"
                help_message = self.show_help()

                chan.send(welcome_message.encode('utf-8'))
                chan.send(help_message.encode('utf-8') + b'\r\n')

                buffer = ""
                while True:
                    data = chan.recv(1024)
                    if not data:
                        break
                    try:
                        buffer += data.decode('utf-8')
                    except UnicodeDecodeError:
                        continue  # Ignore non-UTF-8 data

                    while '\n' in buffer:
                        message, buffer = buffer.split('\n', 1)
                        message = message.strip()
                        print(f"Received from {client_address}: {message}")

                        # Increment total messages count
                        with self.lock:
                            self.total_messages += 1

                        if message.startswith("/"):
                            # Increment command count
                            with self.lock:
                                self.total_commands += 1

                            response = self.handle_command(message, client_address)
                        else:
                            response = message

                        # Add two clear lines before responding
                        clear_lines = "\n\n"
                        chan.send((clear_lines + response + '\r\n').encode('utf-8'))

                        if message == "/logoff":
                            break
            except (ConnectionResetError, BrokenPipeError, KeyboardInterrupt):
                print(f"Connection with {client_address} was interrupted.")
            except Exception as e:
                print(f"Unexpected error with {client_address}: {e}")
            finally:
                # Close client connection and decrement client count
                chan.close()
                with self.lock:
                    self.client_count -= 1
                print(f"Connection with {client_address} closed.")
        except Exception as e:
            print(f"SSH negotiation failed: {e}")
        finally:
            transport.close()

    def handle_command(self, command, client_address):
        # Split command and arguments
        parts = command.split(" ", 1)
        cmd = parts[0].lower()

        if cmd == "/help":
            return self.show_help()

        elif cmd == "/search":
            if len(parts) > 1:
                keyword = parts[1]
                with self.lock:
                    self.search_count += 1
                return self.search_files(keyword)
            else:
                return self.invalid_command(f"Usage: /search <keyword>")

        elif cmd == "/videosearch":
            if len(parts) > 1:
                keyword = parts[1]
                with self.lock:
                    self.videosearch_count += 1
                return self.search_videos(keyword)
            else:
                return self.invalid_command(f"Usage: /videosearch <keyword>")

        elif cmd == "/logoff":
            return f"{COLOR_YELLOW}Logging off...{COLOR_RESET}"

        elif cmd == "/stats":
            return self.get_stats()

        elif cmd == "/uptime":
            return self.get_uptime()

        else:
            return self.invalid_command("Unknown command. Type /help for a list of commands.")

    def invalid_command(self, message):
        return f"{COLOR_RED}Error: {message}{COLOR_RESET}"

    def show_help(self):
        # Return the help message
        help_text = (
            f"{COLOR_BLUE}Available commands:{COLOR_RESET}\r\n"
            f"{COLOR_BLUE}{'Command':<15} {'Description'}{COLOR_RESET}\r\n"
            f"{'-'*40}\r\n"
            f"{COLOR_BLUE}/help{COLOR_RESET:<15} Show this help message\r\n"
            f"{COLOR_BLUE}/search <keyword>{COLOR_RESET:<15} Search files in the FILES/ directory for a keyword\r\n"
            f"{COLOR_BLUE}/videosearch <keyword>{COLOR_RESET:<15} Search for lines containing the keyword in videos.txt\r\n"
            f"{COLOR_BLUE}/logoff{COLOR_RESET:<15} Log off from the server\r\n"
            f"{COLOR_BLUE}/stats{COLOR_RESET:<15} Show server statistics\r\n"
            f"{COLOR_BLUE}/uptime{COLOR_RESET:<15} Show server uptime and start time"
        )
        return help_text

    def search_files(self, keyword):
        # Search for a keyword in files within the FILES/ directory
        matching_files = []
        keyword = keyword.lower()
        for root, dirs, files in os.walk(FILES_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, 'r', errors='ignore') as f:
                    for line_number, line in enumerate(f, 1):
                        if keyword in line.lower():
                            matching_files.append((file_path, line_number, line.strip()))

        if matching_files:
            results = "\r\n".join(f"{i + 1}. {file:<50} {line_number:<5} {line}" for i, (file, line_number, line) in enumerate(matching_files))
            return (
                f"{COLOR_GREEN}Files containing the keyword '{keyword}':{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'No.':<5} {'File':<50} {'Line':<5} {'Content'}{COLOR_RESET}\r\n"
                f"{'-'*100}\r\n{results}"
            )
        else:
            return f"{COLOR_RED}No files found containing the keyword '{keyword}'.{COLOR_RESET}"

    def search_videos(self, keyword):
        # Search for a keyword in the videos.txt file
        matching_lines = []
        keyword = keyword.lower()
        if os.path.exists(VIDEOS_FILE):
            with open(VIDEOS_FILE, 'r', errors='ignore') as f:
                for line_number, line in enumerate(f, 1):
                    if keyword in line.lower():
                        matching_lines.append(f"{line_number:<5} {line.strip()}")

        if matching_lines:
            results = "\r\n".join(matching_lines)
            return (
                f"{COLOR_GREEN}Lines containing the keyword '{keyword}' in {VIDEOS_FILE}:{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Line':<5} {'Content':<50}{COLOR_RESET}\r\n"
                f"{'-'*55}\r\n{results}"
            )
        else:
            return f"{COLOR_RED}No lines found containing the keyword '{keyword}' in {VIDEOS_FILE}.{COLOR_RESET}"

    def get_uptime(self):
        # Calculate and return the server uptime
        uptime_seconds = time.time() - self.start_time
        uptime_string = time.strftime("%H:%M:%S", time.gmtime(uptime_seconds))
        return (
            f"{COLOR_GREEN}Server Uptime (Version {version}):{COLOR_RESET}\r\n"
            f"{COLOR_GREEN}{'Metric':<20} {'Value':<30}{COLOR_RESET}\r\n"
            f"{'-'*50}\r\n"
            f"{COLOR_GREEN}{'Uptime':<20} {uptime_string:<30}{COLOR_RESET}\r\n"
            f"{COLOR_GREEN}{'Start Time':<20} {self.start_datetime:<30}{COLOR_RESET}"
        )

    def get_stats(self):
        # Return server statistics
        with self.lock:
            # Directly call get_uptime() method and format its response correctly
            uptime_stats = self.get_uptime().split('\r\n')[2:]
            uptime_stats_text = "\r\n".join(uptime_stats)

            stats_text = (
                f"{COLOR_BLUE}Server Statistics (Version {version}):{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Metric':<25} {'Value':<10}{COLOR_RESET}\r\n"
                f"{'-'*35}\r\n"
                f"{COLOR_GREEN}{'Current Clients':<25} {self.client_count:<10}{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Total Clients':<25} {self.total_clients:<10}{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Total Messages':<25} {self.total_messages:<10}{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Search Commands':<25} {self.search_count:<10}{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Video Search Commands':<25} {self.videosearch_count:<10}{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Total Commands':<25} {self.total_commands:<10}{COLOR_RESET}\r\n"
                f"{uptime_stats_text}"
            )
            return stats_text

    def start(self):
        # Start the server to accept connections
        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
                    client_thread.start()
                except OSError:
                    break
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            self.server_socket.close()

if __name__ == '__main__':
    server = SSHServer(port=8023)
    server.start()


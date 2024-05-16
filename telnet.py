#!/opt/homebrew/bin/python3.11
# Copyright 2024 by moshix
# A telnet based server to search TEXT documents
# v0.1 humble beginnings
# v0.2 some commands /search 
# v0.3 make it indepedent of capitalization
# v0.4 handl SIGINT (sorta)
# v0.5 tabulate
# v0.6 /stats
# v0.7 /uptime
# v0.8 make /search also search PDFs now !
# v0.9 paginate the output
# v1.0 color code responses nicer 
# v1.1 slight delay for better terminal experience
import socket
import threading
import os
import signal
import time
import PyPDF2
from datetime import datetime
import argparse

# Version information
version = "1.1"

# ANSI color codes for formatting
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[1;32m"
COLOR_BLUE = "\033[1;34m"
COLOR_RED = "\033[1;31m"
COLOR_YELLOW = "\033[1;33m"
COLOR_CYAN = "\033[1;36m"

FILES_DIR = "FILES/"
VIDEOS_FILE = "videos.txt"

class TelnetServer:
    def __init__(self, host='0.0.0.0', port=8023):
        self.host = host
        self.port = port

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Telnet server started on {self.host}:{self.port}")

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

        signal.signal(signal.SIGINT, self.handle_sigint)

    def handle_sigint(self, signum, frame):
        print("\nSIGINT received. Shutting down the server.")
        self.running = False
        self.server_socket.close()

    def handle_client(self, client_socket, client_address):
        with self.lock:
            self.client_count += 1
            self.total_clients += 1
        print(f"Accepted connection from {client_address}")

        try:
            client_socket.sendall(f"\n{COLOR_GREEN}Welcome to the Telnet server! Version: {version}{COLOR_RESET}\r\n".encode('utf-8'))
            client_socket.sendall(self.show_help().encode('utf-8') + b'\r\n')

            buffer = ""
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                buffer += data.decode('utf-8')

                if '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    message = message.strip()
                    print(f"Received from {client_address}: {message}")

                    start_time = time.time()

                    with self.lock:
                        self.total_messages += 1

                    if message.startswith("/"):
                        with self.lock:
                            self.total_commands += 1

                        response = self.handle_command(message)
                    else:
                        response = message

                    response_time = time.time() - start_time
                    response += f"\n{COLOR_CYAN}Response time: {response_time:.4f} seconds{COLOR_RESET}"

                    clear_lines = "\n\n"
                    self.send_response(client_socket, clear_lines + response)

                    if message == "/logoff":
                        break

        except (ConnectionResetError, BrokenPipeError, KeyboardInterrupt):
            print(f"Connection with {client_address} was interrupted.")
        except Exception as e:
            print(f"Unexpected error with {client_address}: {e}")
        finally:
            client_socket.close()
            with self.lock:
                self.client_count -= 1
            print(f"Connection with {client_address} closed.")

    def send_response(self, client_socket, response):
        lines = response.split('\r\n')
        if len(lines) <= 25:
            for line in lines:
                client_socket.sendall((line + '\r\n').encode('utf-8'))
                time.sleep(0.05)
        else:
            for line in lines:
                client_socket.sendall((line + '\r\n').encode('utf-8'))

    def handle_command(self, command):
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
                return self.invalid_command("Usage: /search <keyword>")

        elif cmd == "/videosearch":
            if len(parts) > 1:
                keyword = parts[1]
                with self.lock:
                    self.videosearch_count += 1
                return self.search_videos(keyword)
            else:
                return self.invalid_command("Usage: /videosearch <keyword>")

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

    def paginate_response(self, header, lines, page_size=25):
        paginated_response = []
        for i in range(0, len(lines), page_size):
            page = lines[i:i + page_size]
            paginated_response.append(header + "\r\n" + "\r\n".join(page))
        return "\r\n".join(paginated_response)

    def search_files(self, keyword):
        matching_files = []
        keyword = keyword.lower()
        for root, dirs, files in os.walk(FILES_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith('.pdf'):
                    matches = self.search_pdf(file_path, keyword)
                    if matches:
                        for match in matches:
                            matching_files.append((file_path, match[0], match[1]))
                else:
                    with open(file_path, 'r', errors='ignore') as f:
                        for line_number, line in enumerate(f, 1):
                            if keyword in line.lower():
                                matching_files.append((file_path, line_number, line.strip()))

        if matching_files:
            header = (
                f"{COLOR_GREEN}Files containing the keyword '{keyword}':{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'No.':<5} {'File':<50} {'Line':<5} {'Content'}{COLOR_RESET}\r\n"
                f"{'-'*100}"
            )
            results = [f"{i + 1}. {COLOR_BLUE}{file:<50} {COLOR_YELLOW}{line_number:<5} {COLOR_RESET}{line}" for i, (file, line_number, line) in enumerate(matching_files)]
            return self.paginate_response(header, results)
        else:
            return f"{COLOR_RED}No files found containing the keyword '{keyword}'.{COLOR_RESET}"

    def search_pdf(self, file_path, keyword):
        matches = []
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_number, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text:
                    for line_number, line in enumerate(text.split('\n'), 1):
                        if keyword in line.lower():
                            matches.append((page_number, line.strip()))
        return matches

    def search_videos(self, keyword):
        matching_lines = []
        keyword = keyword.lower()
        if os.path.exists(VIDEOS_FILE):
            with open(VIDEOS_FILE, 'r', errors='ignore') as f:
                for line_number, line in enumerate(f, 1):
                    if keyword in line.lower():
                        matching_lines.append(f"{line_number:<5} {line.strip()}")

        if matching_lines:
            header = (
                f"{COLOR_GREEN}Lines containing the keyword '{keyword}' in {VIDEOS_FILE}:{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'Line':<5} {'Content':<50}{COLOR_RESET}\r\n"
                f"{'-'*55}"
            )
            results = [f"{COLOR_YELLOW}{line}" for line in matching_lines]
            return self.paginate_response(header, results)
        else:
            return f"{COLOR_RED}No lines found containing the keyword '{keyword}' in {VIDEOS_FILE}.{COLOR_RESET}"

    def get_uptime(self):
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
        with self.lock:
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
    parser = argparse.ArgumentParser(description='Start a Telnet server.')
    parser.add_argument('--port', type=int, default=8023, help='Port to run the Telnet server on')
    args = parser.parse_args()

    server = TelnetServer(port=args.port)
    server.start()


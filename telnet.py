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
# v1.2 Fix headers for responses
# v1.3 Properly shut down server with Ctrl-C
# v1.4 Add invocation parameter --delay for first 25 lines
# v1.5 Log to server.log now
# v1.6 recursiverly saearch subdirectories
# v1.7 for too many results, stop and give error msg
# v1.8 insert comments in code.... 
# v1.9 enable searching phrases (indepenent of capitalization)
# invoke with python3 telnet_server.py --port 8023 --delay 0.05 --delay_lines 25 --files_dir FILES/

import socket
import threading
import os
import signal
import time
import PyPDF2
from datetime import datetime
import argparse

# Version information
version = "1.9"

# ANSI color codes for formatting
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[1;32m"
COLOR_BLUE = "\033[1;34m"
COLOR_RED = "\033[1;31m"
COLOR_YELLOW = "\033[1;33m"
COLOR_CYAN = "\033[1;36m"

# Maximum number of search results
MAX_RESULTS = 30

class TelnetServer:
    def __init__(self, host='0.0.0.0', port=8023, delay=0.05, delay_lines=25, files_dir='FILES/'):
        self.host = host
        self.port = port
        self.delay = delay
        self.delay_lines = delay_lines
        self.files_dir = files_dir

        # Initialize server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Telnet server started on {self.host}:{self.port}")

        # Initialize server state and statistics
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
        self.threads = []

        # Log file setup
        self.log_file = open('server.log', 'a')

        # Handle SIGINT (Control-C) to shut down the server gracefully
        signal.signal(signal.SIGINT, self.handle_sigint)

    def handle_sigint(self, signum, frame):
        """Handle SIGINT signal to shut down the server gracefully."""
        print("\nSIGINT received. Shutting down the server.")
        self.running = False
        self.server_socket.close()

        # Close all client connections
        for thread in self.threads:
            thread.join()

        # Close log file
        self.log_file.close()

        print("Server shut down successfully.")

    def log(self, message, client_address=None):
        """Log messages to both the console and log file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{timestamp} - {client_address} - {message}" if client_address else f"{timestamp} - {message}"
        print(log_message)
        self.log_file.write(log_message + '\n')
        self.log_file.flush()

    def handle_client(self, client_socket, client_address):
        """Handle client connections and process commands."""
        with self.lock:
            self.client_count += 1
            self.total_clients += 1
        self.log(f"Accepted connection from {client_address}", client_address)

        try:
            # Send welcome message and help message to the client
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
                    self.log(f"Received command: {message}", client_address)

                    start_time = time.time()

                    with self.lock:
                        self.total_messages += 1

                    if message.startswith("/"):
                        with self.lock:
                            self.total_commands += 1

                        response = self.handle_command(message, client_address)
                    else:
                        response = message

                    response_time = time.time() - start_time
                    response += f"\n{COLOR_CYAN}Response time: {response_time:.4f} seconds{COLOR_RESET}"

                    clear_lines = "\n\n"
                    self.send_response(client_socket, clear_lines + response)

                    if message == "/logoff":
                        break

        except (ConnectionResetError, BrokenPipeError, KeyboardInterrupt):
            self.log(f"Connection with {client_address} was interrupted.", client_address)
        except Exception as e:
            self.log(f"Unexpected error with {client_address}: {e}", client_address)
        finally:
            client_socket.close()
            with self.lock:
                self.client_count -= 1
            self.log(f"Connection with {client_address} closed.", client_address)

    def send_response(self, client_socket, response):
        """Send response to the client with optional delay for the first few lines."""
        lines = response.split('\r\n')
        for i, line in enumerate(lines):
            if i < self.delay_lines:
                client_socket.sendall((line + '\r\n').encode('utf-8'))
                time.sleep(self.delay)
            else:
                client_socket.sendall((line + '\r\n').encode('utf-8'))

    def handle_command(self, command, client_address):
        """Handle commands received from the client."""
        parts = command.split(" ", 1)
        cmd = parts[0].lower()

        if cmd == "/help":
            return self.show_help()

        elif cmd == "/search":
            if len(parts) > 1:
                keyword = parts[1]
                with self.lock:
                    self.search_count += 1
                self.log(f"Search command with keyword: {keyword}", client_address)
                return self.search_files(keyword)
            else:
                return self.invalid_command("Usage: /search <keyword>")

        elif cmd == "/videosearch":
            if len(parts) > 1:
                keyword = parts[1]
                with self.lock:
                    self.videosearch_count += 1
                self.log(f"Video search command with keyword: {keyword}", client_address)
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
        """Return error message for invalid commands."""
        return f"{COLOR_RED}Error: {message}{COLOR_RESET}"

    def show_help(self):
        """Show help message with available commands."""
        help_text = (
            f"{COLOR_BLUE}Available commands:{COLOR_RESET}\r\n"
            f"{COLOR_BLUE}{'Command':<15} {'Description'}{COLOR_RESET}\r\n"
            f"{'-'*40}\r\n"
            f"{COLOR_BLUE}/help{COLOR_RESET:<15} Show this help message\r\n"
            f"{COLOR_BLUE}/search <keyword>{COLOR_RESET:<15} Search files in the specified directory for a keyword\r\n"
            f"{COLOR_BLUE}/videosearch <keyword>{COLOR_RESET:<15} Search for lines containing the keyword in videos.txt\r\n"
            f"{COLOR_BLUE}/logoff{COLOR_RESET:<15} Log off from the server\r\n"
            f"{COLOR_BLUE}/stats{COLOR_RESET:<15} Show server statistics\r\n"
            f"{COLOR_BLUE}/uptime{COLOR_RESET:<15} Show server uptime and start time"
        )
        return help_text

    def paginate_response(self, header, lines, page_size=25):
        """Paginate long responses for better readability."""
        paginated_response = []
        for i in range(0, len(lines), page_size):
            page = lines[i:i + page_size]
            paginated_response.append(header + "\r\n" + "\r\n".join(page))
        return "\r\n".join(paginated_response)

    def search_files(self, keyword):
        """Search files for the given keyword and return the results."""
        matching_files = []
        keyword = keyword.lower()

        # Determine if the keyword is a phrase enclosed in double quotes
        if keyword.startswith('"') and keyword.endswith('"'):
            keyword = keyword[1:-1]  # Remove the double quotes
            is_phrase = True
        else:
            is_phrase = False

        for root, dirs, files in os.walk(self.files_dir):
            for file in files:
                file_path = os.path.join(root, file).replace(self.files_dir, "")
                if file.lower().endswith('.pdf'):
                    matches = self.search_pdf(file_path, keyword, is_phrase)
                    if matches:
                        for match in matches:
                            matching_files.append((file_path, match[0], match[1]))
                else:
                    with open(os.path.join(root, file), 'r', errors='ignore') as f:
                        for line_number, line in enumerate(f, 1):
                            if (is_phrase and keyword in line.lower()) or (not is_phrase and keyword in line.lower().split()):
                                matching_files.append((file_path, f"Line {line_number}", line.strip()))

                # Stop search if too many results are found
                if len(matching_files) > MAX_RESULTS:
                    return f"{COLOR_RED}Too many search results found. Stopping search.{COLOR_RESET}"

        if matching_files:
            header = (
                f"{COLOR_GREEN}Files containing the keyword '{keyword}':{COLOR_RESET}\r\n"
                f"{COLOR_GREEN}{'No.':<5} {'File':<43} {'Location':<10} {'Content'}{COLOR_RESET}\r\n"
                f"{'-'*100}"
            )
            results = [f"{i + 1}. {COLOR_BLUE}{file:<43} {COLOR_YELLOW}{location:<10} {COLOR_RESET}{line}" for i, (file, location, line) in enumerate(matching_files)]
            return self.paginate_response(header, results)
        else:
            return f"{COLOR_RED}No files found containing the keyword '{keyword}'.{COLOR_RESET}"

    def search_pdf(self, file_path, keyword, is_phrase):
        """Search PDF files for the given keyword and return the results."""
        matches = []
        full_path = os.path.join(self.files_dir, file_path)
        with open(full_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_number, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text:
                    for line_number, line in enumerate(text.split('\n'), 1):
                        line_lower = line.lower()
                        if (is_phrase and keyword in line_lower) or (not is_phrase and keyword in line_lower.split()):
                            cleaned_line = line.replace("/bulletmed", "").strip()
                            matches.append((f"Page {page_number}", cleaned_line))
        return matches

    def search_videos(self, keyword):
        """Search videos.txt for the given keyword and return the results."""
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
                f"{COLOR_GREEN}{'Location':<10} {'Content':<50}{COLOR_RESET}\r\n"
                f"{'-'*55}"
            )
            results = [f"{COLOR_YELLOW}{line}" for line in matching_lines]
            return self.paginate_response(header, results)
        else:
            return f"{COLOR_RED}No lines found containing the keyword '{keyword}' in {VIDEOS_FILE}.{COLOR_RESET}"

    def get_uptime(self):
        """Return server uptime information."""
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
        """Return server statistics."""
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
        """Start the Telnet server and handle incoming connections."""
        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
                    self.threads.append(client_thread)
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
    parser.add_argument('--delay', type=float, default=0.05, help='Delay in seconds between lines for short responses')
    parser.add_argument('--delay_lines', type=int, default=25, help='Number of lines to apply the delay to')
    parser.add_argument('--files_dir', type=str, default='FILES/', help='Directory to search files in')
    args = parser.parse_args()

    server = TelnetServer(port=args.port, delay=args.delay, delay_lines=args.delay_lines, files_dir=args.files_dir)
    server.start()


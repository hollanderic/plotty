#!/usr/bin/env python3
import argparse
import sys
import threading
import time
import queue
import subprocess
import urllib.request
import re
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

def parse_arguments():
    parser = argparse.ArgumentParser(description="Plot values from CSV strings.")
    parser.add_argument("source", help="Source of the CSV strings (file path, URL, or user@host:path)")
    parser.add_argument("columns", nargs='+', type=int, help="List of column indices to plot. First is X, rest are Ys.")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow the source (like tail -f)")
    parser.add_argument("-t", "--title", action="store_true", help="Use first row as titles")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="Baud rate for serial connection (default: 115200)")
    return parser.parse_args()

class DataSource:
    def __init__(self, source, follow=False):
        self.source = source
        self.follow = follow
        self.queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._read_loop)
        self.thread.daemon = True
    
    def connect(self):
        """
        Establishes connection to the source.
        Returns the first line if available (e.g. for headers), or None.
        This method should block until connection is established (e.g. SSH password).
        """
        return None

    def start(self):
        self.thread.start()
        
    def stop(self):
        self.running = False

    def _read_loop(self):
        raise NotImplementedError

    def get_data(self):
        lines = []
        try:
            while True:
                line = self.queue.get_nowait()
                lines.append(line)
        except queue.Empty:
            pass
        return lines

class LocalFileSource(DataSource):
    def __init__(self, source, follow=False):
        super().__init__(source, follow)
        self.file_handle = None

    def connect(self):
        try:
            self.file_handle = open(self.source, 'r')
            # returning the first line for header check without consuming it if we need to put it back?
            # actually for -t we want to consume it. If not -t, we might need to "peek" or just read normally.
            # But the requirement says "use first row... as labels". 
            # If we read it here, we should probably return it.
            # If the caller decides it's data, we need a way to push it back or handle it.
            # Simpler: Always read first line here. If caller doesn't want it as header, 
            # we need to inject it into queue?
            # Let's peek.
            pos = self.file_handle.tell()
            line = self.file_handle.readline()
            self.file_handle.seek(pos)
            return line.strip() if line else None
        except FileNotFoundError:
            print(f"Error: File '{self.source}' not found.")
            sys.exit(1)

    def _read_loop(self):
        if not self.file_handle:
            return 
            
        try:
            # If we verified connection, we are good.
            # self.connect() was called before start().
            # But we reset the file pointer in connect().
            # So we just read from start.
            while self.running:
                line = self.file_handle.readline()
                if line:
                    self.queue.put(line.strip())
                else:
                    if self.follow:
                        time.sleep(0.1)
                    else:
                        break
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
        finally:
            if self.file_handle:
                self.file_handle.close()

class HttpSource(DataSource):
    def connect(self):
        # Verify connectivity
        try:
            with urllib.request.urlopen(self.source) as response:
                 # Just peek first line? urllib response is not seekable usually.
                 # We might need to reopen or just buffer the first line.
                 line = response.readline()
                 self.first_line = line # Store it to be pushed to queue first
                 return line.decode('utf-8').strip() if line else None
        except Exception as e:
             print(f"Error connecting to URL '{self.source}': {e}")
             sys.exit(1)

    def _read_loop(self):
        try:
             # Re-open might be safer for streams, or use the cached first line
             # But if we consumed first line in connect, we might lose it if we don't handle it.
             # Actually, simpler: read loop opens connection. connect() just polls?
             # But request says "do not display plot until ... connected".
             # So connect() must succeed.
             
             # Re-requesting.
            with urllib.request.urlopen(self.source) as response:
                 if hasattr(self, 'first_line_consumed') and self.first_line_consumed:
                     # Skip first line
                     response.readline()
                     
                 for line in response:
                     if not self.running:
                         break
                     self.queue.put(line.decode('utf-8').strip())
                     
            if self.follow:
                while self.running:
                    time.sleep(1)

        except Exception as e:
             print(f"Error reading from URL '{self.source}': {e}")
             sys.exit(1)

import subprocess
import os
try:
    import serial
except ImportError:
    serial = None

class SshSource(DataSource):
    def __init__(self, source, follow=False):
         super().__init__(source, follow)
         self.process = None

    def connect(self):
        try:
            user_host, path = self.source.split(":")
            # For connect, we want to ensure we can read.
            # We start the process HERE.
            # This allows password prompt to happen on stdout/stderr before we return.
            
            cmd_remote = f"tail -f {path}" if self.follow else f"cat {path}"
            ssh_cmd = ["ssh", user_host, cmd_remote]
            
            # Use Popen. stdout=PIPE is needed to read data.
            # stderr=None allows stderr to go to terminal for password prompt!
            self.process = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1)
            
            # Try to read one line to verify connection and get header
            # This WILL BLOCK until password is entered and command starts outputting.
            # If password fails, ssh exits, process.stdout closes?
            
            first_line = self.process.stdout.readline()
            if not first_line:
                # Process died?
                ret = self.process.poll()
                if ret is not None and ret != 0:
                     print(f"SSH command failed with exit code {ret}")
                     sys.exit(1)
                return None
            
            return first_line.strip()
            
        except Exception as e:
            print(f"Error connecting via SSH '{self.source}': {e}")
            sys.exit(1)

    def _read_loop(self):
        # Process already started in connect()
        if not self.process:
             return

        try:
            # We already read the first line in connect().
            # If it wasn't a header (or even if it was), we might need to handle it.
            # If the user wanted it as header, it's consumed.
            # If not, it should be data.
            
            # The issue: connect() consumes one line. 
            # We need to put it back if it's not a header.
            # Let's handle injection in main or Source.
            
            while self.running:
                line = self.process.stdout.readline()
                if not line:
                    if self.process.poll() is not None:
                         break
                    continue
                self.queue.put(line.strip())
                
            self.process.terminate()
            
        except Exception as e:
            print(f"Error reading from SSH '{self.source}': {e}")
            sys.exit(1)

class SerialSource(DataSource):
    def __init__(self, source, baudrate=115200, follow=False):
        super().__init__(source, follow)
        self.baudrate = baudrate
        self.serial_conn = None

    def connect(self):
        if serial is None:
            print("Error: pyserial module not installed. Please run 'pip install pyserial'.")
            sys.exit(1)
            
        try:
            self.serial_conn = serial.Serial(self.source, self.baudrate, timeout=1)
            # Read a line to verify and return as potential header
            # Serial might need some time or bytes might be partial. 
            # readline with timeout=1 should return something or empty.
            # If we want to block until data comes:
            self.serial_conn.timeout = None # Blocking
            line = self.serial_conn.readline()
            return line.decode('utf-8', errors='ignore').strip() if line else None
        except Exception as e:
            print(f"Error connecting to Serial Port '{self.source}': {e}")
            sys.exit(1)

    def _read_loop(self):
        if not self.serial_conn:
            return
            
        try:
            while self.running:
                # Serial readline is blocking if timeout is None
                line = self.serial_conn.readline()
                if line:
                    self.queue.put(line.decode('utf-8', errors='ignore').strip())
                else:
                    # Should not happen in blocking mode unless port closed
                    break
        except Exception as e:
             print(f"Error reading from Serial Port: {e}")
             # Don't exit here, maybe just stop loop
        finally:
             if self.serial_conn and self.serial_conn.is_open:
                 self.serial_conn.close()

def get_source_handler(source, follow, baudrate=115200):
    if source.startswith("http://") or source.startswith("https://"):
        return HttpSource(source, follow)
    elif "@" in source and ":" in source: 
        return SshSource(source, follow)
    elif source.startswith("/dev/tty") or source.upper().startswith("COM"):
        return SerialSource(source, baudrate, follow)
    else:
        return LocalFileSource(source, follow)

def parse_line(line, columns):
    try:
        parts = line.split(',')
        if len(parts) <= max(columns):
            return None
        
        values = []
        for col in columns:
            values.append(float(parts[col]))
        return values
    except ValueError:
        return None



def main():
    args = parse_arguments()
    
    # Set dark theme
    plt.style.use('dark_background')
    
    source_handler = get_source_handler(args.source, args.follow, args.baud)
    if not source_handler:
        print(f"Error: Could not determine source type for '{args.source}'")
        sys.exit(1)
        
    print("Connecting to source... (if SSH, please enter password if prompted)")
    first_line = source_handler.connect()
    
    # Handle Header
    labels = [f"Col {c}" for c in args.columns[1:]]
    if args.title and first_line:
        # Parse first line as labels
        parts = first_line.split(',')
        new_labels = []
        try:
            for c in args.columns[1:]:
                if c < len(parts):
                    new_labels.append(parts[c].strip())
                else:
                    new_labels.append(f"Col {c}")
            labels = new_labels
        except:
             print("Warning: Could not parse title line, using default labels.")
        
        # Mark first line as consumed in source if needed?
        # For HttpSource, we marked valid invalid.
        if isinstance(source_handler, HttpSource):
            source_handler.first_line_consumed = True
        # For SshSource, it's already consumed from stdout.
        # For LocalFileSource, we seeked back, so we need to consume it now if we want to skip it.
        if isinstance(source_handler, LocalFileSource):
             source_handler.file_handle.readline() # Consume it
             
    elif first_line:
        # first_line is data. We need to push it to queue or handle it.
        # But data loop hasn't started.
        # For SSH, it's consumed. For HTTP, we peeked/cached? 
        # For File, we seeked back.
        
        if isinstance(source_handler, SshSource):
             source_handler.queue.put(first_line)
        # HttpSource: connect() just peeked/read. 
        # If we re-request in read_loop, we get it again.
        if isinstance(source_handler, HttpSource):
             source_handler.first_line_consumed = False
        # LocalFileSource: we seeked back, so read_loop will get it.
        pass

    source_handler.start()
    
    # Data storage
    x_data = []
    y_data_list = [[] for _ in range(len(args.columns) - 1)] # List of lists for Y columns
    
    fig, ax = plt.subplots()
    lines = []
    for i in range(len(args.columns) - 1):
        line, = ax.plot([], [], label=labels[i])
        lines.append(line)
    
    if len(args.columns) > 1 or args.title:
        ax.legend()
    
    # Use title from X column if available? Or just "Column X"
    x_label = f"Column {args.columns[0]}"
    if args.title and first_line:
         parts = first_line.split(',')
         if args.columns[0] < len(parts):
             x_label = parts[args.columns[0]].strip()
             
    ax.set_xlabel(x_label)
    ax.set_ylabel("Values")
    ax.set_title(f"Source: {args.source}")
    fig.canvas.manager.set_window_title(args.source)
    ax.grid(True, color='gray', linestyle='-', linewidth=0.5, alpha=0.6)
    
    def update(frame):
        # Fetch all available data from queue
        new_lines = source_handler.get_data()
        updated = False
        for line in new_lines:
            val = parse_line(line, args.columns)
            if val:
                x_data.append(val[0])
                for i, y_val in enumerate(val[1:]):
                    y_data_list[i].append(y_val)
                updated = True
        
        if updated:
            for i, line in enumerate(lines):
                line.set_data(x_data, y_data_list[i])
            
            # Rescale view
            ax.relim()
            ax.autoscale_view()
        
        if not args.follow and not source_handler.thread.is_alive() and source_handler.queue.empty():
             # If not following and source is done, we could stop animation, 
             # but keeping plot open is usually desired.
             pass

        return lines

    # Use FuncAnimation
    ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    
    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        source_handler.stop()

if __name__ == "__main__":
    main()

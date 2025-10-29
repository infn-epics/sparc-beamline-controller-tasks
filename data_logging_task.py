#!/usr/bin/env python3
"""
Example data logging task that demonstrates file I/O and periodic operations.

This task logs data to a file at regular intervals.
"""

import cothread
from datetime import datetime
from pathlib import Path
from typing import Any
from task_base import TaskBase


class DataLoggingTask(TaskBase):
    """Example task that logs data to files."""
    
    def initialize(self):
        """Initialize the data logging task."""
        self.logger.info("Initializing data logging task")
        
        # Get task parameters
        self.log_interval = self.parameters.get('log_interval', 10.0)
        self.log_directory = Path(self.parameters.get('log_directory', './logs'))
        self.log_format = self.parameters.get('log_format', 'csv')
        
        # Create log directory if it doesn't exist
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"{self.name}_{timestamp}.{self.log_format}"
        self.log_file_path = self.log_directory / log_filename
        
        # Initialize state
        self.log_count = 0
        self.last_log_time = cothread.GetTime()
        
        # Write CSV header if applicable
        if self.log_format == 'csv':
            with open(self.log_file_path, 'w') as f:
                f.write("timestamp,value1,value2,value3,status\n")
        
        self.logger.info(f"Logging to: {self.log_file_path}")
        self.logger.info(f"Log interval: {self.log_interval} seconds")
    
    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting data logging task execution")
        
        while self.running:
            # Only log if task is enabled
            enabled = self.get_pv('ENABLE')
            
            current_time = cothread.GetTime()
            time_since_last_log = current_time - self.last_log_time
            
            if enabled and time_since_last_log >= self.log_interval:
                self._log_data()
                self.last_log_time = current_time
                # increment cycle counter when a log event occurs
                self.step_cycle()
            
            # Sleep for a short time
            cothread.Sleep(0.5)
    
    def _log_data(self):
        """Log current data to file."""
        try:
            # Read values to log
            value1 = self.get_pv('VALUE1') or 0.0
            value2 = self.get_pv('VALUE2') or 0.0
            value3 = self.get_pv('VALUE3') or 0.0
            
            timestamp = datetime.now().isoformat()
            
            # Write to file based on format
            if self.log_format == 'csv':
                with open(self.log_file_path, 'a') as f:
                    f.write(f"{timestamp},{value1},{value2},{value3},OK\n")
            else:
                with open(self.log_file_path, 'a') as f:
                    f.write(f"[{timestamp}] V1={value1}, V2={value2}, V3={value3}\n")
            
            # Update counters
            self.log_count += 1
            self.set_pv('LOG_COUNT', self.log_count)
            self.set_pv('LAST_LOG_TIME', timestamp)
            
            self.logger.debug(f"Logged entry {self.log_count}")
            
        except Exception as e:
            self.logger.error(f"Error logging data: {e}", exc_info=True)
            self.set_status('ERROR')
            self.set_message(f"Error: {str(e)}")
    
    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up data logging task")
        self.set_status('END')
        self.set_message('Stopped')
        self.logger.info(f"Total log entries: {self.log_count}")
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle writes to specific PVs.
        
        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        if pv_name == 'RESET_COUNT':
            if value:
                self.logger.info("Resetting log count")
                self.log_count = 0
                self.set_pv('LOG_COUNT', 0)
                self.set_pv('RESET_COUNT', 0)

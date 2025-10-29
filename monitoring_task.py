#!/usr/bin/env python3
"""
Example monitoring task that demonstrates the task framework.

This task monitors a set of input PVs, performs calculations,
and updates output PVs accordingly.
"""

import cothread
from typing import Any
from task_base import TaskBase


class MonitoringTask(TaskBase):
    """Example task that monitors values and computes statistics."""
    
    def initialize(self):
        """Initialize the monitoring task."""
        self.logger.info("Initializing monitoring task")
        
        # Get task parameters
        self.update_rate = self.parameters.get('update_rate', 1.0)
        self.calculation_type = self.parameters.get('calculation_type', 'average')
        
        # Access beamline configuration if needed
        beamline = self.beamline_config.get('beamline', 'unknown')
        self.logger.info(f"Running on beamline: {beamline}")
        
        # Initialize internal state
        self.sample_count = 0
        
        self.logger.info(f"Update rate: {self.update_rate} Hz")
        self.logger.info(f"Calculation type: {self.calculation_type}")
    
    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting monitoring task execution")
        
        while self.running:
            # Only process if task is enabled
            enabled = self.get_pv('ENABLE')
            
            if enabled:
                self._process_cycle()
                # increment cycle counter when active
                self.step_cycle()
            else:
                self.logger.debug("Task disabled, skipping cycle")
            
            # Sleep based on update rate
            cothread.Sleep(1.0 / self.update_rate)
    
    def _process_cycle(self):
        """Process one monitoring cycle."""
        try:
            # Read input PVs
            input1 = self.get_pv('INPUT1') or 0.0
            input2 = self.get_pv('INPUT2') or 0.0
            input3 = self.get_pv('INPUT3') or 0.0
            
            # Perform calculation based on type
            if self.calculation_type == 'average':
                result = (input1 + input2 + input3) / 3.0
            elif self.calculation_type == 'sum':
                result = input1 + input2 + input3
            elif self.calculation_type == 'max':
                result = max(input1, input2, input3)
            elif self.calculation_type == 'min':
                result = min(input1, input2, input3)
            else:
                result = 0.0
            
            # Update output PVs
            self.set_pv('OUTPUT_RESULT', result)
            
            # Update sample count
            self.sample_count += 1
            self.set_pv('SAMPLE_COUNT', self.sample_count)
            
            # Update status and message
            self.set_message(f"Processed {self.sample_count} samples")
            
            self.logger.debug(f"Cycle {self.sample_count}: result={result:.3f}")
            
        except Exception as e:
            self.logger.error(f"Error in processing cycle: {e}", exc_info=True)
            self.set_status('ERROR')
            self.set_message(f"Error: {str(e)}")
    
    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up monitoring task")
        self.set_status('END')
        self.set_message('Stopped')
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle writes to specific PVs.
        
        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        if pv_name == 'RESET':
            if value:
                self.logger.info("Resetting sample count")
                self.sample_count = 0
                self.set_pv('SAMPLE_COUNT', 0)
                self.set_pv('RESET', 0)  # Reset the reset button
        
        elif pv_name in ['INPUT1', 'INPUT2', 'INPUT3']:
            self.logger.debug(f"{pv_name} updated to {value}")

#!/usr/bin/env python3
"""
Laser synchronization task - example based on laser_synch_softIOC.py

This task demonstrates:
- Reading from external EPICS PVs
- Computing averages and corrections
- Controlling external devices
- Implementing interlocks
"""

import cothread
import numpy as np
from typing import Any
from epics import caget, caput
from task_base import TaskBase


class LaserSynchTask(TaskBase):
    """Laser synchronization control task."""
    
    def initialize(self):
        """Initialize the laser synch task."""
        self.logger.info("Initializing laser synch task")
        
        # Get task parameters
        self.loop_period = self.parameters.get('loop_period', 0.2)
        self.avg_num = self.parameters.get('avg_num', 10)
        self.interlock_buff_length = self.parameters.get('interlock_buff_length', 10)
        
        # Get external PV names from parameters
        self.prefix_redpitaya = self.parameters.get('prefix_redpitaya', '')
        self.prefix_motor = self.parameters.get('prefix_motor', '')
        self.pv_laser_amp_llrf = self.parameters.get('pv_laser_amp_llrf', '')
        
        # Initialize buffers
        self.corr_buff = []
        self.err_buff = []
        self.laser_amp_buff = []
        
        # Initialize external devices
        if self.prefix_redpitaya:
            self._init_redpitaya()
        
        if self.prefix_motor:
            self._init_motor()
        
        self.logger.info(f"Loop period: {self.loop_period} s")
        self.logger.info(f"Average number: {self.avg_num}")
    
    def _init_redpitaya(self):
        """Initialize RedPitaya settings."""
        try:
            caput(f"{self.prefix_redpitaya}:RESET_ACQ_CMD", "1")
            caput(f"{self.prefix_redpitaya}:ACQ_TRIGGER_SRC_CMD", "NOW")
            caput(f"{self.prefix_redpitaya}:IN2_GAIN_CMD", "High")
            caput(f"{self.prefix_redpitaya}:ACQ_AVERAGING_CMD", "Off")
            caput(f"{self.prefix_redpitaya}:DIGITAL_P4_DIR_CMD", "1")
            caput(f"{self.prefix_redpitaya}:DIGITAL_P4_STATE_CMD", "0")
            caput(f"{self.prefix_redpitaya}:OUT1_FREQ_SP", "0")
            caput(f"{self.prefix_redpitaya}:OUT1_ENABLE_CMD", "1")
            self.logger.info("RedPitaya initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize RedPitaya: {e}")
    
    def _init_motor(self):
        """Initialize motor settings."""
        try:
            caput(f"{self.prefix_motor}:m0.HLM", "2.6")
            self.logger.info("Motor initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize motor: {e}")
    
    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting laser synch task execution")
        
        while self.running:
            # Only process if task is enabled
            if not self.get_pv('ENABLE'):
                self.logger.debug("Task disabled, skipping cycle")
                cothread.Sleep(self.loop_period)
                continue
            
            try:
                self._process_cycle()
                # increment cycle counter when active
                self.step_cycle()
            except Exception as e:
                self.logger.error(f"Error in processing cycle: {e}", exc_info=True)
                self.set_status('ERROR')
                self.set_message(f"Error: {str(e)}")
            
            # Sleep for loop period
            cothread.Sleep(self.loop_period)
    
    def _process_cycle(self):
        """Process one control cycle."""
        # Read PLL status from RedPitaya
        pll_on = False
        if self.prefix_redpitaya:
            pll_on = caget(f"{self.prefix_redpitaya}:DIGITAL_P4_STATE_STATUS")
        
        # Update PLL status PV
        self.set_pv('PLL_ON', int(pll_on))
        
        # Reset average if requested
        if self.get_pv('AVG_RESET'):
            self.corr_buff = []
            self.set_pv('AVG_RESET', 0)
            self.logger.info("Average buffer reset")
        
        # Acquire correction waveform
        if self.prefix_redpitaya:
            caput(f"{self.prefix_redpitaya}:START_SS_ACQ_CMD", 1)
            wave_corr = caget(f"{self.prefix_redpitaya}:IN2_DATA_MONITOR")
            
            if wave_corr is not None:
                # Calculate average over specified range
                avg_start = int(self.get_pv('AVG_START') or 0)
                avg_stop = int(self.get_pv('AVG_STOP') or len(wave_corr))
                
                corr_value = np.mean(wave_corr[avg_start:avg_stop+1])
                self.set_pv('CORR', corr_value)
                
                # Update correction buffer
                self.corr_buff.append(corr_value)
                if len(self.corr_buff) > self.avg_num:
                    self.corr_buff.pop(0)
                
                # Update average
                corr_avg = np.mean(self.corr_buff)
                self.set_pv('CORR_AVG', corr_avg)
        
        # Update laser amplitude buffer
        if self.pv_laser_amp_llrf:
            laser_amp = caget(self.pv_laser_amp_llrf)
            if laser_amp is not None:
                self.laser_amp_buff.append(laser_amp)
                if len(self.laser_amp_buff) > self.interlock_buff_length:
                    self.laser_amp_buff.pop(0)
        
        # Update error buffer
        if self.prefix_redpitaya:
            wave_err = caget(f"{self.prefix_redpitaya}:IN1_DATA_MONITOR")
            if wave_err is not None:
                self.err_buff.append(np.max(wave_err))
                if len(self.err_buff) > self.interlock_buff_length:
                    self.err_buff.pop(0)
        
        # Implement interlock logic
        if pll_on:
            pll_err_tsh = self.get_pv('PLL_ERR_TSH') or 1.0
            laser_amp_tsh = self.get_pv('LASER_AMP_TSH') or 0.0
            
            err_count = sum(1 for e in self.err_buff if e > pll_err_tsh)
            amp_count = sum(1 for a in self.laser_amp_buff if a < laser_amp_tsh)
            
            if err_count == self.interlock_buff_length or amp_count == self.interlock_buff_length:
                if self.prefix_redpitaya:
                    caput(f"{self.prefix_redpitaya}:DIGITAL_P4_STATE_CMD", "0")
                self.logger.warning("Interlock triggered - PLL turned OFF")
                pll_on = False
        
        # Disable tracking if PLL is off
        if not pll_on:
            self.set_pv('TRACKING_ON', 0)
        
        # Perform tracking if enabled
        tracking_on = self.get_pv('TRACKING_ON')
        if tracking_on:
            corr_avg = self.get_pv('CORR_AVG') or 0.0
            tracking_tsh = self.get_pv('TRACKING_TSH') or 0.1
            tracking_step = self.get_pv('TRACKING_STEP') or 0.01
            
            if abs(corr_avg) > tracking_tsh and self.prefix_motor:
                step = tracking_step if corr_avg > 0 else -tracking_step
                caput(f"{self.prefix_motor}:m0.RLV", str(step))
                self.logger.debug(f"Tracking: moving motor by {step}")
        
        # Update message with status
        self.set_message(f"PLL:{'ON' if pll_on else 'OFF'} Track:{'ON' if tracking_on else 'OFF'}")
    
    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up laser synch task")
        
        # Turn off PLL
        if self.prefix_redpitaya:
            try:
                caput(f"{self.prefix_redpitaya}:DIGITAL_P4_STATE_CMD", "0")
            except Exception as e:
                self.logger.error(f"Error turning off PLL: {e}")
        
        self.set_status('END')
        self.set_message('Stopped')
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle PV writes.
        
        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        if pv_name == 'AVG_RESET' and value:
            self.logger.info("Average reset requested")
        elif pv_name == 'TRACKING_ON':
            self.logger.info(f"Tracking {'enabled' if value else 'disabled'}")
        elif pv_name in ['AVG_START', 'AVG_STOP']:
            self.logger.debug(f"{pv_name} updated to {value}")

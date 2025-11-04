#!/usr/bin/env python3
"""
Motor control task - demonstrates using Ophyd motor devices

This task:
- Monitors motors using Ophyd device instances
- Detects when motors are moving
- Logs motor name and position when movement is detected
"""

import cothread
from typing import Any
from task_base import TaskBase


class CheckMotorMovement(TaskBase):
    """Task for monitoring motors using Ophyd devices."""
    
    def initialize(self):
        """Initialize the motor control task."""
        self.logger.info("Initializing motor control task")
        
        # Get task parameters
        self.update_rate = self.parameters.get('update_rate', 1.0)
        self.motors_list = self.parameters.get('motors', [])
        self.switchoff_names = self.parameters.get('switchoff', [])
        # Get motor devices from Ophyd devices
        self.motors = {}
        self.switches={}
        if not self.motors_list:
            self.logger.warning("No motors provided; task will not monitor any motors.")
        else:
            # Expand names: allow passing IOC/group prefixes like 'tml-ch1' to match all devices with that prefix
            all_devices = self.list_devices()
            for requested in self.motors_list:
                # Direct exact match first
                dev = self.get_device(requested)
                if dev:
                    self.motors[requested] = dev
                    self.logger.info(f"Found motor device: {requested}")
                    continue
            ## found switchoff devices
            for requested in self.switchoff_names:
                dev = self.get_device(requested)
                if dev:
                    self.switches[requested] = dev
                    self.logger.info(f"Found switchoff device: {requested}")
                    continue

              
        if not self.motors:
            self.logger.warning("No motor devices found!")
        
        # Log available devices
        # available_devices = self.list_devices()
        #self.logger.info(f"Available Ophyd devices: {available_devices}")
        
        # Track previous moving state to detect changes
        self.previous_moving_state = {}
        for motor_name in self.motors.keys():
            self.previous_moving_state[motor_name] = False
        
        self.logger.info(f"Initialized with {len(self.motors)} motors")
    
    def motor_moved_callback(self, motor_name: str, position: Any):
        """Normalized motor movement callback: called with motor name and new position."""
        if self.get_cycle() > 10:
            self.logger.info(f"Motor {motor_name} moved to position {position}")
            if not self.get_pv('ENABLE'):
                return
            # Set switchoff devices to 0 (CLOSE) upon motor movement
            for sw_name, sw in self.switches.items():
                try:
                    sw.set(0)
                    self.logger.info(f"Switchoff device {sw_name} set to 0 (CLOSE) due to motor movement.")
                except Exception as e:
                    self.logger.error(f"Error setting switchoff device {sw_name}: {e}")


    def make_user_readback_callback(self, motor_name: str):
        """Adapter: map user_readback (timestamp, value, **kwargs) to motor_moved_callback."""
        def callback(timestamp=None, value=None, **kwargs):
            # Forward just the value (position) along with the motor name
            self.motor_moved_callback(motor_name, value)
        return callback

    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting motor control task execution")
        for motor_name, motor in self.motors.items():
            self.logger.info(f"Subscribing to user_readback for motor: {motor_name}")

            motor.user_readback.subscribe(self.make_user_readback_callback(motor_name))


        while self.running:
            # Only process if task is enabled
            if not self.get_pv('ENABLE'):
                self.logger.debug("Task disabled, skipping cycle")
                
                cothread.Sleep(1.0 / self.update_rate)
                continue
            
            try:
                self._monitor_motors()
                # increment cycle counter
                self.step_cycle()
            except Exception as e:
                self.logger.error(f"Error in processing cycle: {e}", exc_info=True)
                self.set_status('ERROR')
                self.set_message(f"Error: {str(e)}")
            
            # Sleep based on update rate
            cothread.Sleep(1.0 / self.update_rate)
    
    def _monitor_motors(self):
        """Monitor motors and detect movement."""
        for motor_name, motor in self.motors.items():
            try:
                # Check if motor is moving
                is_moving = False
                position = None

                # moving may be a property (standard Ophyd) or a method (custom TML motor)
                if hasattr(motor, 'moving'):
                    mv = getattr(motor, 'moving')
                    is_moving = mv() if callable(mv) else bool(mv)

                # position may be a property or a method
                if hasattr(motor, 'position'):
                    pos_attr = getattr(motor, 'position')
                    position = pos_attr() if callable(pos_attr) else pos_attr
                else:
                    # Fallback to user_readback if available
                    rb = getattr(motor, 'user_readback', None)
                    try:
                        position = rb.get() if rb is not None else None
                    except Exception:
                        position = None
                
                # Detect state change from not moving to moving
                if is_moving and not self.previous_moving_state[motor_name]:
                    self.logger.info(f"Motor {motor_name} started moving - Position: {position}")
                
                # Detect state change from moving to not moving
                elif not is_moving and self.previous_moving_state[motor_name]:
                    self.logger.info(f"Motor {motor_name} stopped - Final position: {position}")
                
                # Log position while moving
                elif is_moving:
                    self.logger.info(f"Motor {motor_name} is moving - Current position: {position}")
                
                # Update tracking state
                self.previous_moving_state[motor_name] = is_moving
                
                # Update PVs if they exist
                pv_name = f"{motor_name}_POS"
                if pv_name in self.pvs:
                    self.set_pv(pv_name, position)
                
                pv_moving = f"{motor_name}_MOVING"
                if pv_moving in self.pvs:
                    self.set_pv(pv_moving, int(is_moving))

                self.set_pv("MOVING", int(is_moving))

            except Exception as e:
                self.logger.error(f"Error monitoring {motor_name}: {e}")
    
    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up motor control task")
        self.set_status('END')
        self.set_message('Stopped')
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle PV writes.
        
        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        self.logger.debug(f"PV {pv_name} set to {value}")

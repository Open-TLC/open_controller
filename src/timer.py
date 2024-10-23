# -*- coding: utf-8 -*-
"""The timer.

This module implements system timer for clockwork_tc

"""
# Coopyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
import time 

class Timer():
    """Timer for handling time steps and conversions"""
    def __init__(self, timer_prm):
        self.time_step = timer_prm['time_step']
        self.time_multiplier = timer_prm['real_time_multiplier']
        self.start_rtime = time.time()
        self.cur_rtime = time.time()
        self.steps = 0
        self.last_update = self.cur_rtime
        # This is used to compensate for the time drift as integrator
        self.aggregate_time_drift = 0.0 

    def __str__(self):
        return "Timer, {} steps and {} seconds".format(self.steps, self.seconds)

    def reset(self):
        """Starts the timer from zero"""
        self.steps = 0
        self.start_rtime = time.time()
        self.cur_rtime = time.time()-self.start_rtime

    def tick(self):
        """One time step forward"""
        self.steps += 1
        self.cur_rtime = (time.time()-self.start_rtime) * self.time_multiplier 
        self.aggregate_time_drift += self.get_time_since_last_update() - self.time_step


    def sleep_tick(self):
        self.cur_rtime = (time.time()-self.start_rtime) * self.time_multiplier 

    def get_time_since_last_update(self):
        """Returns the last update time and updates the counter to current time
           This is operated by the tick-function
        """
        last_update_before_reset = self.last_update
        self.last_update = time.time()
        last_update_diff = self.last_update - last_update_before_reset
        return last_update_diff

    def reset_time_step(self):
        """Resets the aggregate time drift
           This is called by the controller after it starts again after stopping
           (by the UI)
        """
        self.aggregate_time_drift = 0.0
        self.last_update = time.time()
        
    
    
    def get_next_time_step(self):
        """Returns the next time step in seconds"""
        # We compensate the time step with the aggregate time drift
        # This works as an integrator and adjusts the time step to match the real time
        next_corrected_time_step = self.time_step - self.aggregate_time_drift
        if next_corrected_time_step < 0.0:
            next_corrected_time_step = 0.0
        return next_corrected_time_step
    

    @property
    def real_seconds(self):
        """Returns real time in seconds from simulation start"""
        return(round(self.cur_rtime,5))
        

    @property
    def seconds(self):
        """Returns time in seconds, rounded up to three decimals"""
        return round(self.steps * self.time_step, 5)
      
    
    @seconds.setter
    def seconds(self, new_seconds):
        # Sets _steps_ to closest second value
        self.steps = round(new_seconds/self.time_step,5)  # one might consider flooring?
       
    
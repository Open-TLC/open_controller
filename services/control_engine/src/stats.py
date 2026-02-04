# -*- coding: utf-8 -*-
"""The logger

This module implements logging amd stats counting functionality
for clockwork_tc

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
#
#


import pandas as pd
from signal_group import SignalGroup

# just for debug
from confread import GlobalConf
from timer import Timer

def main():
    timer=Timer(0.1)
    sys_cnf = GlobalConf().cnf
    grp = SignalGroup(timer, 'kari', sys_cnf['controller']['signal_groups']['default'])
    log = StatLogger(timer)
    print("adding data")
    log.add_data(grp, 'Green start')
    timer.tick()
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Amber start')
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    timer.tick()
    timer.tick()
    timer.tick()
    timer.tick()
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    log.add_data(grp, 'Green start')
    print(log.group_data.get_events_dataframe())



class StatLogger():
    """Logging the traffic control events"""
    def __init__(self, system_timer):
        self.system_timer = system_timer
        self.group_data = GroupData()

    def add_data(self, sender, data):
        """Adds group data"""

        # Note: iPython reload seem so mess this up
        if isinstance(sender, SignalGroup):
            self.group_data.add_data(self.system_timer.seconds, sender, data)


    def reset(self):
        self.group_data.data = []

# trying git
class GroupData():
    """Type for saving group level data"""
    def __init__(self):
        self.data = []
        #columns = ['time', 'group', 'state']
        #self.group_changes = pd.DataFrame(columns=columns)
        # self.group_changes.set_index('time')

    def add_data(self, time, sender, state):
        """Adds new data item (event) to the object"""
        name = sender.group_name
        new_event = [time, name, state]
        self.data.append(new_event)
        # print(self.data)

    def get_events_dataframe(self):
        """Creates a dataframe from the list of events"""
        columns = ['time', 'group', 'state']
        df = pd.DataFrame(columns=columns, data=self.data)
        # self.group_changes.set_index('time')
        return df



# Class for storing simulation output as text
class SimOutput():
    """Class for storing simulation output as text"""
    def __init__(self):
        self.output = "Simoout started\n"

    def add_line(self, line):
        """Adds a line to the output"""
        self.output += line + "\n"

    def get_output(self):
        """Returns the output"""
        return self.output


if __name__ == "__main__":
    runsim()
    #main()

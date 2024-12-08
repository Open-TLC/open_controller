"This Unit containd handlers for the traditional detector inputs and outputs."

class Detector:
    """A class for handling simple detector inputs and outputs"""

    def __init__(self, name, params, status = None):
        self.name = name
        self.params = params
        self.status = status # Will be true or false
        self.trigger_functions = [] # Functions to trigger if status changes

    def __str__(self):
        return "Detector: {} - {}".format(self.name, self.status)
    
    def set_status(self, status):
        """Sets the status of the detector"""
        if self.status != status:
            # This is not yet functional
            for func in self.trigger_functions:
                func(status)
            print("Detector: {} - {}".format(self.name, status))

        self.status = status

class DetectorLogic(Detector):
    """A class for creating new detectors by combining imputs from existing detectors"""
    def __init__(self, name, params, status = None):
        super().__init__(name, params, status)
    
    def __str__(self):
        return "DetLogic: {} - {}".format(self.name, self.status)
    


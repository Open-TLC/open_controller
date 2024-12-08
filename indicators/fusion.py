"""
    This unit contains functionality for handling calculation ofoutputs based
    on multible inputps. In essence we formulate a "Field Of View" and map 
    relevant inputs into it. All data manipualtaion and calculation needed 
    for outputs will be handled here
"""


class Lane:
    """Lane indicators contained"""
    def __init__(self):
        self.input_dets = []
        self.output_dets = []
        self.input_radars = []
        %
    


class FieldOfView:
    """
        A class for defining field of view, this is set of inputs that are 
        relevant for the calculation of output values. Typically this is an
        approach for the traffic in a certain area."""
    
    def __init__(self, name, params):
        self.name = name
        self.params = params
        # Inputs
        self.radars = []
        self.detectors = []





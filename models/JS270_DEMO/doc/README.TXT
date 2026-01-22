DEMO-models
Helsinki KYMP 21.11.2024
___________________________________

1. General structure

- contr = json files for running open controller
- cfgFiles = Sumo main configuration files
- net = Sumo network model
- rou = routes and traffic
- add = detectors (e1 & e3), stations, vehicle types
- tll = fixed timne signal control files
- out = default file output folder
- gui = gui settings
- doc = documentation, readme.txt

This structure is compatible with Simulation Datatool

2. The open controller configuration files:

- JS270_DEMO_e1.json
  - e1 detectors only
    - for requests and extending

- JS270_DEMO_e1PT.json
  - e1 detectors only
    - for requests and extending
    - Basic priority for trams from Välimerenkatu (group3)

- JS270_DEMO_e3.json
  - e1 detectors for requests
  - e3 detectors for smart entenders

- JS270_DEMO_e3PT.json
  - e1 detectors for requests
  - e3 detectors for smart entenders
  - smart priority for trams

- JS270_DEMO_HW.json
  - e1 detectors only
    - for requests and extending
    - to be used in Hardware-in-the-loop simulation demo


   

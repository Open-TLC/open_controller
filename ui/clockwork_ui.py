# This is unit for running the Clockwork controller with agiven params 
# and then running the UI for it.
#
# Run this app with `python clockwork_ui.py` and
# visit http://127.0.0.1:8050/ in your web browser.


# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#
# Copyright 2023 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

from dash import Dash
from dash import html, dcc, callback, Output, Input, dash_table
import dash_leaflet as dl
import plotly.express as px
import pandas as pd
import asyncio
from threading import Thread
from nats.aio.client import Client as NATS
import json
from message_storage import MessageStorage

import sys
# Maybe this should be set as module in the future?
sys.path.insert(0, 'clockwork/')
from signal_group_controller import PhaseRingController


STATUS_CHANNEL = "clockwork.status.JS270" # DEBUG

DEFAULT_CONF_FILE = "testmodel/nats_controller.json"
STATUS_CHANNEL_PREFIX = "clockwork.status"
COMMAND_CHANNEL = "clockwork.command"
CONF_CHANNEL = "clockwork.conf"
UPDATE_INTERVAL = 1000 # ms
NATS_REQ_TIMEOUT = 10 # s
NUMBER_OF_GROUPS = 4

# For running locally
#NATS_SERVER = "localhost:4222"
# For running in docker
NATS_SERVER = "nats:4222"
# For testing with the itc unit
#NATS_SERVER = "10.8.0.36:4222"
# 270 (the test intersection)
#NATS_SERVER = "10.8.0.201:4222"
#NATS_SERVER = "192.168.0.101:4222"


params = [
    'Weight', 'Torque', 'Width', 'Height',
    'Efficiency', 'Power', 'Displacement'
]

app = Dash(__name__, suppress_callback_exceptions=True)





# These will be GLOBAL variables
current_status = "NOTHING HERE"
nats=None
# Note: we can only operate one controller for one user at a time
# We could consider storing this as some kind of session variable
controller = None

# This is for providing information about the NATS messages for the UI
message_storage = None


# UI to be relayed via nats
start_sim_pressed = False
stop_sim_pressed = False

test_counter = 0 # DEBUG
#
# This is the Async part (NATS)
#
async def some_print_task():
    """Some async function"""
    global test_counter
    while True:
        await asyncio.sleep(2)
        test_counter += 2


async def commands_handler():
    """Another async function"""
    global nats
    global start_sim_pressed
    global stop_sim_pressed

    while True:
        await asyncio.sleep(1)
        if start_sim_pressed:
            print("Starting simulation")
            await nats.publish(COMMAND_CHANNEL, "start".encode())
            start_sim_pressed = False
            continue # Next await
        if stop_sim_pressed:
            print("Stopping simulation")
            await nats.publish(COMMAND_CHANNEL, "stop".encode())
            stop_sim_pressed = False
            continue # Next await


async def async_main():
    """Main async function"""
    global current_status
    global nats
    nats = NATS()
    await nats.connect(NATS_SERVER)
    async def message_handler(msg):
        global current_status
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        current_status = data
    await nats.subscribe(STATUS_CHANNEL, cb=message_handler)
    await asyncio.gather(some_print_task(), commands_handler())

def async_main_wrapper():
    """Not async Wrapper around async_main to run it as target1function of Thread"""
    asyncio.run(async_main())



# 
# This is the dash part
#

def build_tabs():
    return html.Div(
        id="tabs",
        className="tabs",
        children=[
            dcc.Tabs(
                id="app-tabs",
                value="tab1",
                className="custom-tabs",
                children=[
                    dcc.Tab(
                        id="Ops-tab",
                        label="Controller Operation",
                        value="tab1",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                    ),
                    dcc.Tab(
                        id="Settings-tab",
                        label="Controller Settings",
                        value="tab2",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                    ),
                    dcc.Tab(
                        id="Messages-tab",
                        label="Messages",
                        value="tab4",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                    ),
                    dcc.Tab(
                        id="Map-tab",
                        label="Map",
                        value="tab3",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                    ),
                ],
            ),
        html.Div(id="app-content")    
        ],
    )

def serve_layout():
    return build_tabs()


def serve_layout_tab1():
    
    return html.Div([
        html.H1("Clockwork controller"),
        dcc.Store(id='memory'),
        html.H2("Controller operations"),
        html.Button('Start controller', id='start-sim', n_clicks=0),
        html.Button('Stop controller', id='stop-sim', n_clicks=0),
        html.Div(id='button-output', style={'whiteSpace': 'pre-line'}),
        html.Div(id='button-output2', style={'whiteSpace': 'pre-line'}),
        html.H2("Controller status"),
        html.Div(id='status-output', style={'whiteSpace': 'pre-line'}),
        dcc.Interval(
            id='interval-component',
            interval=UPDATE_INTERVAL, # in milliseconds
            n_intervals=0
        ),
        html.H1("SSH-interface"),
        html.H2("Group operations")
    ])



def serve_layout_tab2():
    return html.Div([
        html.Button('Get Conf', id='get-conf', n_clicks=0),
        html.Button('Save Conf', id='save-conf', n_clicks=0),
        html.Div(id='conf-saved', style={'whiteSpace': 'pre-line'}),
        html.H1("Configuration"),
        html.H2("Groups"),        
        dash_table.DataTable(
            id='groups-table',
            dropdown={
                    'request_type': {
                        'options': [
                            {'label': 'detector', 'value': 'detector'},
                            {'label': 'fixed', 'value': 'fixed'}
                        ]
                    },
                    'phase_request': {
                        'options': [
                            {'label': 'true', 'value': 'true'},
                            {'label': 'false', 'value': 'false'}
                        ]
                    },
                    'green_end': {
                        'options': [
                            {'label': 'after_ext', 'value': 'after_ext'},
                            {'label': 'remain', 'value': 'remain'}
                        ]
                    }
                    
                },
            editable=True),
        html.Div(id='grp-conf-edited', style={'whiteSpace': 'pre-line'}),
        html.H2("Intergreens"),
        dash_table.DataTable(
            id='intergreens-table',
            editable=True),
        html.Div(id='ig-conf-edited', style={'whiteSpace': 'pre-line'}),
        
        html.H2("Phases"),
        dash_table.DataTable(
            id='phases-table',
            editable=True),
        # Can we put dropdown here?
        html.Div(id='phase-conf-edited', style={'whiteSpace': 'pre-line'}),


        html.H2("Detectors"),
        dash_table.DataTable(
            id='detectors-table',
            editable=True),        

        html.H2("Lanes"),
        dash_table.DataTable(
            id='lanes-table',
            editable=True),

        html.Div(id='table-dropdown-container'),
        html.Div(id='conf-output', style={'whiteSpace': 'pre-line'}),
    ])


def serve_layout_tab3():
    return html.Div([
        html.H1("Map"),
        dl.Map([
            dl.TileLayer(),
            dl.Polyline(weight=5, positions=[[60.1571487965302, 24.922002019804452], [60.15967368797896, 24.921544378437073], [60.160028463816865, 24.921485939754497]])
        ], center=[60.160236780347496, 24.92134939836445], zoom=17, style={'height': '50vh'})
        ])

def serve_layout_tab4():
    return html.Div([
        html.H1("Messages"),
        html.H2("Detectors"),
        dash_table.DataTable(
            id='det-messages-table',
            editable=False),
        html.H2("Groups"),
        dash_table.DataTable(
            id='group-messages-table',
            editable=False),

        html.H2("control_messages"),
        html.Button('Group 1 On', id='group-1-on', n_clicks=0),    
        html.Button('Group 1 Off', id='group-1-off', n_clicks=0),
        html.Div(id='group-1-on-output', style={'whiteSpace': 'pre-line'}),
        html.Div(id='group-1-off-output', style={'whiteSpace': 'pre-line'}),
        html.H2("Raw messages"),
        html.Div(id='nats-messages', style={'whiteSpace': 'pre-line'}),
        dcc.Interval(
            id='interval-component-messages',
            interval=UPDATE_INTERVAL, # in milliseconds
            n_intervals=0
        )
        ])



app.layout = serve_layout()

async def update_message_container():
    "This function will set up the message container and subscribe to the messages"
    global message_storage
    global nats
    # We only set this up if nats is live
    while not nats:
        # Wait for nats to be set up
        await asyncio.sleep(1)

    
    message_storage = MessageStorage()
    async def handle_messages(msg):
        global message_storage
        channel = msg.subject
        message = msg.data.decode()
        message_storage.add_message(channel, message)
    await nats.subscribe("detector.status.*", cb=handle_messages)
    await nats.subscribe("group.status.*.*", cb=handle_messages)
    while True:
        await asyncio.sleep(1)
        #print(message_storage.get_detector_messages())

@app.callback(
    [Output("app-content", "children")],
    [Input("app-tabs", "value")]
)
def render_tab_content(tab_switch):
    if tab_switch == "tab1":
        return [serve_layout_tab1()]
    elif tab_switch == "tab2":
        return [serve_layout_tab2()]
    elif tab_switch == "tab3":
        return [serve_layout_tab3()]
    else:
        return [serve_layout_tab4()]





#Input('refresh', 'n_clicks'),
@callback(
    Output('status-output', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_output(value):
    global current_status
    value = current_status
    return '{}'.format(value)


@callback(
    Output('nats-messages', 'children'),
    Output('det-messages-table', 'data'), 
    Output('det-messages-table', 'columns'),
    Output('group-messages-table', 'data'), 
    Output('group-messages-table', 'columns'),
    Input('interval-component-messages', 'n_intervals')
)
async def update_output2(value):
    global message_storage
    if message_storage is None:
        asyncio.create_task(update_message_container())
        return "No messages yet", None, None # This should likely respond wit an empty table
    else:    
        raw_messages = message_storage.get_latest_messages()
        det_messages_df = message_storage.get_detector_messages_as_df()
        det_messages_cols =  [{"name": i, "id": i} for i in det_messages_df.columns]
        group_messages_df = message_storage.get_group_messages_as_df()
        group_messages_cols =  [{"name": i, "id": i} for i in group_messages_df.columns]


        return [
            raw_messages,
            det_messages_df.to_dict('records'), 
            det_messages_cols,
            group_messages_df.to_dict('records'),
            group_messages_cols
            ]
        
#Input('refresh', 'n_clicks'),
@callback(
    Output('button-output', 'children'),
    Input('start-sim', 'n_clicks'),
    prevent_initial_call=True
)
def start_sim(value):
    print("Start button pressed")
    global start_sim_pressed
    start_sim_pressed = True
    return "START BUTTON PRESSED"

#Input('refresh', 'n_clicks'),
@callback(
    Output('button-output2', 'children'),
    Input('stop-sim', 'n_clicks'),
    prevent_initial_call=True
)
def stop_sim(value):
    print("Stop button pressed")
    global stop_sim_pressed
    stop_sim_pressed = True

    return "STOP BUTTON PRESSED"
    

#
# TEST FUNCTIONS FOR SENDING GROUP COMMANDS
# 


@callback(
    Output('group-1-on-output', 'children'),
    Input('group-1-on', 'n_clicks'),
    prevent_initial_call=True
)
async def set_group_1_on(value):
    #print("Start button pressed")
    global nats
    message = '{"id": "group.control.270.1", "tstamp": "2023-10-30T12:01:09.453+00:00", "substate": "1", "group": 1, "green": true }'
    channel = "group.control.270.1"
    if nats is not None:
        await nats.publish(channel, message.encode())
    return "Group 1 on"


@callback(
    Output('group-1-off-output', 'children'),
    Input('group-1-off', 'n_clicks'),
    prevent_initial_call=True
)
async def set_group_1_off(value):
    #print("Start button pressed")
    global nats
    message = '{"id": "group.control.270.1", "tstamp": "2023-10-30T12:01:09.453+00:00", "substate": "1", "group": 1, "green": false }'
    channel = "group.control.270.1"
    if nats is not None:
        await nats.publish(channel, message.encode())
    return "Group 1 off"


#
# Edit functions
#

@callback(
    Output('grp-conf-edited', 'children'),
    Input('groups-table', 'data'),
    Input('groups-table', 'columns'),
    prevent_initial_call=True)
async def conf_edited_groups(rows, columns):
    global controller
    global nats
    errors = controller.update_group_params(rows)
    if errors is None:
        rep = await nats.request(CONF_CHANNEL, json.dumps(controller.get_conf_as_dict()).encode(), timeout=NATS_REQ_TIMEOUT)
        if rep == "Ok":
            return "Conf edited and saved"
        else:
            return "Conf edited but NOT saved"
    else:
        return errors

@callback(
    Output('ig-conf-edited', 'children'),
    Input('intergreens-table', 'data'),
    Input('intergreens-table', 'columns'),
    prevent_initial_call=True)
async def conf_edited_groups(rows, columns):
    global controller
    global nats
    errors = controller.update_ig_params(rows)
    if errors is None:
        rep = await nats.request(CONF_CHANNEL, json.dumps(controller.get_conf_as_dict()).encode(), timeout=NATS_REQ_TIMEOUT)
        if rep == "Ok":
            return "Conf edited and saved"
        else:
            return "Conf edited but NOT saved"
    else:
        return errors

@callback(
    Output('phase-conf-edited', 'children'),
    Input('phases-table', 'data'),
    Input('phases-table', 'columns'),
    prevent_initial_call=True)
async def conf_edited_groups(rows, columns):
    global controller
    global nats
    errors = controller.update_phase_params(rows)
    if errors is None:
        rep = await nats.request(CONF_CHANNEL, json.dumps(controller.get_conf_as_dict()).encode(), timeout=NATS_REQ_TIMEOUT)
        if rep == "Ok":
            return "Conf edited and saved"
        else:
            return "Conf edited but NOT saved"
    else:
        return errors



@callback(
    [Output('conf-saved', 'children')],
    Input('save-conf', 'n_clicks'),
    prevent_initial_call=True
)
async def save_conf(value):
    print("Get conf button pressed")
    global nats
    global controller
    if nats is not None:
        print("Saving conf")       
        rep = await nats.request(COMMAND_CHANNEL, "save_conf".encode(), timeout=NATS_REQ_TIMEOUT)
        rep_string = rep.data.decode().strip()
        if rep_string == "OK":
            return ["Conf saved"]
        else:
            return [str(rep)]
    return None



@callback(
    [Output('groups-table', 'data'), 
     Output('groups-table', 'columns'),
     Output('intergreens-table', 'data'), 
     Output('intergreens-table', 'columns'),
     Output('phases-table', 'data'), 
     Output('phases-table', 'columns'),
     Output('lanes-table', 'data'),
     Output('lanes-table', 'columns')
     ],
    
    Input('get-conf', 'n_clicks'),
    prevent_initial_call=True
)
async def get_conf_groups(value):
    print("Get conf button pressed")
    global nats
    global controller
    conf = ""
    if nats is not None:
        rep = await nats.request(CONF_CHANNEL, "get_conf".encode(), timeout=NATS_REQ_TIMEOUT)
        conf = json.loads(rep.data.decode())
        # Note: we have no timer for this controller
        controller = PhaseRingController(conf, None)

        # GROUPS
        grp_params_df = controller.get_group_params_as_df()
        grp_cols =  [{"name": i, "id": i} for i in grp_params_df.columns]
        for col in grp_cols:
            if col["name"] in ["request_type", "phase_request", "green_end"]:
                col["presentation"]="dropdown"

            if col["name"] in ["name", "channel"]:
                col["editable"]=False

        # INTERGREENS
        ig_params_df = controller.get_intergreens_as_df()
        ig_cols =  [{"name": i, "id": i} for i in ig_params_df.columns]
        

        # PHASES
        phases_df = controller.get_phases_as_df()
        phases_cols =  [{"name": i, "id": i} for i in phases_df.columns]
        for col in phases_cols:
            col["presentation"]="dropdown"

        # LANES
        lanes_df = controller.get_lane_params_as_df()
        lanes_cols =  [{"name": i, "id": i} for i in lanes_df.columns]
        

        return [
            grp_params_df.to_dict('records'), 
            grp_cols,
            ig_params_df.to_dict('records'), 
            ig_cols,
            phases_df.to_dict('records'), 
            phases_cols,
            lanes_df.to_dict('records'),
            lanes_cols
            ]

    return None

@callback(
    [Output('detectors-table', 'data'), Output('detectors-table', 'columns')],
    Input('get-conf', 'n_clicks'),
    prevent_initial_call=True
)
async def get_conf_detectors(value):
    columns=(
        [{'id': 'Model', 'name': 'Model'}] +
        [{'id': p, 'name': p} for p in params]
    )
    data=[
        dict(Model=i, **{param: 0 for param in params})
        for i in range(1, 5)
        ]
        
    return data, columns




if __name__ == '__main__':
    #asyncio.create_task(get_status())
    print("Test")
    th = Thread(target=async_main_wrapper)
    th.start()
    
    app.run(use_reloader=False, debug=True, host="0.0.0.0", port=8050) # run the app
    th.join()
    #asyncio.run(get_status())
    
    print("Test2")
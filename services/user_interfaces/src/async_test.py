from flask import Flask, jsonify
import asyncio
from threading import Thread
from nats.aio.client import Client as NATS

# Dash
import dash
from dash import dcc
from dash import html
from dash import callback


from dash.dependencies import Input, Output
import requests
import plotly.graph_objects as go 

# ** Constants **

UPDATE_INTERVAL = 1000 # ms
STATUS_CHANNEL = "clockwork.status.JS270"
NATS_SERVER = "localhost:4222"

test_counter = 0
current_status = "unknown"
nats = None 
# ** Async Part **

async def some_print_task():
    """Some async function"""
    global test_counter
    while True:
        await asyncio.sleep(2)
        print("Adding two to counter")
        test_counter += 2


async def another_task():
    """Another async function"""
    while True:
        await asyncio.sleep(3)
        print("Another Task")


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
    await asyncio.gather(some_print_task(), another_task())


def async_main_wrapper():
    """Not async Wrapper around async_main to run it as target function of Thread"""
    asyncio.run(async_main())


# ** Dash Part **:
app = dash.Dash()

app.layout = html.Div([

    # html.Div([
    #     html.Iframe(src="https://www.flightradar24.com",
    #                 height=500,width=200)
    # ]),
    html.H1("Clockwork controller"),
    html.H2("Controller status"),
        html.Div(id='status-output', style={'whiteSpace': 'pre-line'}),
        dcc.Interval(
            id='interval-component',
            interval=UPDATE_INTERVAL, # in milliseconds
            n_intervals=0
        ),
    html.H1("SSH-interface")

])

@callback(
    Output('status-output', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_output(value):
    global test_counter
    value = "counter value: + " + str(test_counter)
    value = current_status + "\n" + value
    return value




if __name__ == '__main__':
    # run all async stuff in another thread
    th = Thread(target=async_main_wrapper)
    th.start()
    app.run_server(debug=True)
    th.join()
# WebSUMO viewer — plan

## The requirement

**OC runs the simulation. We add a NATS interface so it can be viewed.**

That is the whole requirement. It is not "option N" of anything. Do not
restate it in terms of WebSUMO's `INTEGRATION_ROADMAP.md` — that menu
enumerates choices by how much WebSUMO owns, and adopting its framing
drags in assumptions that are not ours. Read WebSUMO's repo for facts
(subject names, payload shapes) and never for the shape of the work.

Integrated mode is what it has always been: a plain Python program taking
command-line params and a conf file, starting SUMO and the controllers
over TraCI. It stays that. Nothing here makes it a service.

## Principles (binding)

If a step appears to require breaking one, the step is wrong.

1. **No changes to existing OC operations.** We only *add*. Nothing in
   OC's current behaviour — control logic, existing subjects, existing
   confs, detector handling, signal application — changes. With the
   interface off, OC behaves exactly as it does today, byte for byte.

2. **Maximum separation from the rest of OC.** This interface has its own
   lifecycle. It does not spread into OC's modules and OC's modules do
   not depend on it. Deletable by removing one file and its call sites.

3. **Clean, readable code in OC's idiom — over cleverness.** Follow the
   conventions already in `services/simengine/src/`. No performance
   tricks, no compressed one-liners, no abstraction invented for this
   feature. Between "fast" and "obvious", pick obvious.

4. **All interface code lives in one file, and it is tested.** Every
   traci↔NATS operation is in a single module. The only edits elsewhere
   are the call sites that invoke it.

## Budget

A breach is a stop, not a judgement call. If any of these is about to be
exceeded, stop and report instead of deciding it is justified.

1. **Zero new configuration.** No conf keys, no command-line flags, no
   defaults to invent.
2. **Zero timing logic in the interface.** No rate, no throttle, no
   decimation. The engine's timer and `timer_mode` own cadence; the
   interface rides the update tick that already drives the controllers,
   and whatever that produces is the cadence.
3. **One new file, one call site per engine.** Nothing else in the repo
   is touched — not docker, not `outputs.py`, not the README, not other
   bugs noticed along the way.
4. **No new abstraction.** Functions. Not a class hierarchy, not a
   facade, not a background thread.
5. **A diff that fits on one screen** — roughly 120 lines total.
6. **No plan longer than this page.** The previous 447-line plan became
   the place design decisions were hidden. Constraints belong in the
   commit message.

## Process

**The complete diff is shown before anything is run.** No processes
launched, no containers touched, no "verification" against running
infrastructure until the diff has been read.

The NATS broker and the WebSUMO viewer container are existing, working
infrastructure. They are not part of this work and are not to be
started, stopped, rebuilt or reconfigured.

## Why this is not an `outputs.py` plugin

An *output* in OC's sense is operational data the controller produces as
part of its job — detector statuses, group statuses, radar detections —
consumed by other OC components. This stream is a rendering surface: how
a person watches the simulation, the same way `sumo-gui`'s X11 traffic is
not an OC output. Nothing in OC consumes it and no OC behaviour depends
on it. `outputs.py` stays exactly as it is.

## The one open decision

Where the scenario name and network file come from: derived from the
sumocfg the conf already points at, or stated explicitly. Everything else
in this change is mechanical.

## Failures not to repeat

Recorded because each one cost a full revert:

- **Framing the work as "Option 2", then "Option 3"** of WebSUMO's
  roadmap. Same mistake twice, different number.
- **Inventing a rate knob** (`state_rate_hz`), then a wall-clock
  throttle, then a background-thread facade — three abstractions
  Principle 3 already forbade.
- **Answering "how do I run this?" with docker commands**, because
  containers happened to be running, after being told integrated mode is
  a plain program.
- **Tearing down working NATS and viewer containers** that were never
  part of the task.
- **Running things before showing the diff.**

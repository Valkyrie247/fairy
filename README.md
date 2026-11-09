# Tug-of-War Multiplayer Game over UDP with Mininet + SDN

## Network layout

- h1 (10.0.0.1): Player 1
- h2 (10.0.0.2): Player 2
- h3 (10.0.0.3): authoritative Tug-of-War game server
- h4 (10.0.0.4): background traffic generator
- s1 and s2: Open vSwitch switches
- s1--s2: shared bottleneck; QoS is configured on `s1-eth4` and `s2-eth2`
- Controller: OS-Ken / OpenFlow 1.3 on 127.0.0.1:6653

The controller learns MAC addresses and forwards traffic. IPv4 packets with
DSCP 46 are assigned OVS queue 1. Queue 1 receives a 4 Mbps minimum rate;
the default queue receives a 0.5 Mbps minimum rate. The total HTB rate is 5 Mbps.

## 1. Install dependencies in Ubuntu

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 iproute2
```

Create and activate a virtual environment outside the Windows shared folder:

```bash
mkdir -p ~/cn-venv
python3 -m venv ~/cn-venv
source ~/cn-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install os-ken
```

Check:

```bash
python -c "import os_ken; print('OS-Ken working')"
which osken-manager
```

If `python3 -m venv` fails, install `python3-venv` with apt.

## 2. Put the project files in one folder

Keep these files together:
- `topology.py`
- `controller.py`
- `configure_qos.sh`
- `traffic_test.sh`
- your team's existing `server.py`, `client.py`, and `common.py`

Make shell scripts executable:

```bash
chmod +x configure_qos.sh traffic_test.sh
```

## 3. Optional DSCP game packet marking

The game client and server already read the `GAME_DSCP` environment variable.
Set `GAME_DSCP=46` for the prioritized run; leave it unset for baseline.
No manual code edits are required.

## 4. Start the controller

Terminal 1:

```bash
cd /path/to/project
source ~/cn-venv/bin/activate
osken-manager controller.py --ofp-tcp-listen-port 6653
```

Leave it running.

## 5. Start Mininet

Terminal 2:

```bash
cd /path/to/project
sudo python3 topology.py
```

At the Mininet prompt:

```text
mininet> net
mininet> pingall
```

Expected: all four hosts should be reachable. Do not continue until `pingall`
reports 0% packet loss.

## 6. Configure priority queues

At the Mininet prompt:

```text
mininet> sh ./configure_qos.sh priority
mininet> sh ovs-vsctl list Port s1-eth4
mininet> sh ovs-vsctl list Port s2-eth2
```

For the baseline run, use:

```text
mininet> sh ./configure_qos.sh baseline
```

## 7. Start the game

At the Mininet prompt, start the server on h3 (the command runs in the foreground):

```text
mininet> h3 python3 server.py --host 10.0.0.3 --port 9999 &
```

For the **priority** run, start it with DSCP marking instead:

```text
mininet> h3 env GAME_DSCP=46 python3 server.py --host 10.0.0.3 --port 9999 &
```

Stop the previous server before switching modes (e.g. `h3 pkill -f 'python3 server.py'` in the Mininet CLI).

To open graphical Pygame clients (requires a working X11 display), use:

```text
mininet> xterm h1 h2
```

In the two host terminals, run each client with these **priority-mode** commands:

```text
h1: env GAME_DSCP=46 python3 client.py --host 10.0.0.3 --port 9999 --name Alice
h2: env GAME_DSCP=46 python3 client.py --host 10.0.0.3 --port 9999 --name Bob
```

For **baseline**, use the same server/client commands without `env GAME_DSCP=46`.
Use `GAME_DSCP=46` only for the prioritised run (including the server).
Restart the server and clients between runs so they use the intended DSCP setting.
The exact client arguments should match your existing `client.py --help`.

## 8. Generate competing background traffic

First, start an iperf3 server on h3:

```text
mininet> h3 iperf3 -s -p 5201 > /tmp/iperf-server.log 2>&1 &
```

Then generate UDP traffic from h4 to h3:

```text
mininet> h4 bash traffic_test.sh 30 /tmp/fairy-priority.json
```

The offered load (8 Mbps) is greater than the 5 Mbps bottleneck in **both**
baseline and priority modes, so the comparison uses the same congestion level.
For baseline, run `h4 bash traffic_test.sh 30 /tmp/fairy-baseline.json`.
Run each mode three times, keeping the test duration and game input frequency
similar. Watch client RTT and pending counts; the iperf3 JSON output contains
background traffic receiver jitter, loss and throughput. Game RTT/pending are
visible in the client UI but not automatically exported to CSV.

## 9. Measurements to record

For each mode, run at least three trials and record:

| Metric | How to obtain it |
|---|---|
| Game RTT | Existing client's ping/RTT display |
| Game jitter | Variation between consecutive game RTT samples; manual calculation is needed (client does not export samples) |
| Background UDP loss | `iperf3` receiver output |
| Background jitter | `iperf3` receiver output |
| Throughput | `iperf3` receiver bitrate |
| Queue configuration | `ovs-vsctl list QoS` and `ovs-vsctl list Queue` |

Do not invent results. Record the actual output from your trials. Keep the
background traffic rate and duration identical between baseline and priority.

## 10. Useful checks

From the Mininet CLI:

```text
mininet> sh ovs-vsctl show
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s2
mininet> sh ovs-vsctl list QoS
mininet> sh ovs-vsctl list Queue
mininet> h1 ping -c 4 10.0.0.3
```

To exit Mininet:

```text
mininet> exit
```

Stop the controller with Ctrl+C in Terminal 1.

## Important notes

1. The controller expects game IPv4 packets to carry DSCP 46. Enable it on
   both the client and the server with `GAME_DSCP=46` in priority mode.
2. Queue configuration is attached to both ends of the inter-switch link so
   player-to-server and server-to-player traffic can be shaped.
3. `iperf3` traffic uses port 5201, while the game uses UDP port 9999.
4. If the OS-Ken command is not found, activate the virtual environment in
   the controller terminal.
5. If your existing game server binds to `0.0.0.0`, that is also acceptable;
   clients should still connect to `10.0.0.3`.

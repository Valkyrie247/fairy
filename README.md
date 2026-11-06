# Tug-of-War Multiplayer Game over UDP with Mininet + SDN

## Network layout

- h1 (10.0.0.1): Player 1
- h2 (10.0.0.2): Player 2
- h3 (10.0.0.3): authoritative Tug-of-War game server
- h4 (10.0.0.4): background traffic generator
- s1 and s2: Open vSwitch switches
- s1--s2: shared bottleneck; QoS is configured on `s1-eth3` and `s2-eth3`
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

## 3. Mark game UDP packets as DSCP 46

Do this in **both** the existing client and server code, immediately after
each UDP socket is created.

Add `import os` with the other imports, then after `socket.socket(...)` add:

```python
if os.getenv("GAME_DSCP") == "46":
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 46 << 2)
```

Use the actual socket variable name in each file (`self.sock` in the client
or `self.sock`/`self.socket` in the server). The `46 << 2` value sets the
DSCP field to 46 (Expedited Forwarding).

The environment variable makes it possible to compare:
- Baseline: do not set `GAME_DSCP`
- Priority: set `GAME_DSCP=46`

If your socket variable has a different name, apply the option to that socket.

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
mininet> sh ovs-vsctl list Port s1-eth3
mininet> sh ovs-vsctl list Port s2-eth3
```

For the baseline run, use:

```text
mininet> sh ./configure_qos.sh baseline
```

## 7. Start the game

At the Mininet prompt, start the server on h3:

```text
mininet> h3 python3 server.py --host 10.0.0.3 --port 9999
```

If your server uses different CLI arguments, use the arguments documented
inside your existing `server.py`.

In separate Ubuntu terminals, open Mininet CLI sessions to run the clients:

```text
mininet> xterm h1 h2
```

If xterm is unavailable, use the Mininet host command from separate terminal
sessions or run the clients from the Mininet CLI in the background:

```text
mininet> h1 env GAME_DSCP=46 python3 client.py --host 10.0.0.3 --port 9999 --name Alice
mininet> h2 env GAME_DSCP=46 python3 client.py --host 10.0.0.3 --port 9999 --name Bob
```

Use `GAME_DSCP=46` only for the prioritised run. Omit it for baseline.
The exact client arguments should match your existing `client.py --help`.

## 8. Generate competing background traffic

First, start an iperf3 server on h3:

```text
mininet> h3 iperf3 -s -p 5201 > /tmp/iperf-server.log 2>&1 &
```

Then generate UDP traffic from h4 to h3:

```text
mininet> h4 iperf3 -c 10.0.0.3 -u -b 8M -t 30 -p 5201
```

The offered load (8 Mbps) is greater than the configured 5 Mbps bottleneck,
so it creates contention. Run the same test once in baseline mode and once
in priority mode.

## 9. Measurements to record

For each mode, run at least three trials and record:

| Metric | How to obtain it |
|---|---|
| Game RTT | Existing client's ping/RTT display |
| Game jitter | Variation between consecutive game RTT samples; calculate mean absolute difference |
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

1. The controller expects game IPv4 packets to carry DSCP 46. Without the
   socket marking change, the controller will treat them as ordinary traffic.
2. Queue configuration is attached to both ends of the inter-switch link so
   player-to-server and server-to-player traffic can be shaped.
3. `iperf3` traffic uses port 5201, while the game uses UDP port 9999.
4. If the OS-Ken command is not found, activate the virtual environment in
   the controller terminal.
5. If your existing game server binds to `0.0.0.0`, that is also acceptable;
   clients should still connect to `10.0.0.3`.

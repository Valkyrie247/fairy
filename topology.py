#!/usr/bin/env python3
"""Mininet topology for the Tug-of-War SDN project.

h1, h2 = players; h3 = game server; h4 = background traffic generator.
s1--s2 is the shared bottleneck where OVS QoS is configured.
Run with: sudo python3 topology.py
"""
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


class TugOfWarTopo(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        h4 = self.addHost("h4", ip="10.0.0.4/24")

        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s2)
        self.addLink(h4, s1)
        # The inter-switch link is the shared bottleneck.
        self.addLink(s1, s2)


def main():
    topo = TugOfWarTopo()
    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )
    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    try:
        info("*** Starting Mininet network\n")
        net.start()
        info("*** Network ready. Run 'net' and 'pingall' in the Mininet CLI.\n")
        info("*** QoS ports: s1-eth3 and s2-eth3 (the inter-switch link).\n")
        info("*** Game server: h3 (10.0.0.3); players: h1/h2; traffic: h4.\n")
        CLI(net)
    finally:
        info("*** Stopping network\n")
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()

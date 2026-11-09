#!/usr/bin/env python3
"""OpenFlow 1.3 learning switch with DSCP-based game traffic prioritisation.

Game packets marked DSCP 46 are assigned OVS queue 1.
All other packets use the default queue.
Run: osken-manager controller.py --ofp-tcp-listen-port 6653
"""
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet, ipv4


class TugOfWarController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TugOfWarController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser

        # Send packets with no matching flow to the controller.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("Switch %s connected (OpenFlow 1.3)", datapath.id)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        instructions = [
            parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)
        ]
        kwargs = dict(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        if buffer_id is not None and buffer_id != ofp.OFP_NO_BUFFER:
            kwargs["buffer_id"] = buffer_id
        datapath.send_msg(parser.OFPFlowMod(**kwargs))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        if eth.ethertype == 0x88cc:  # LLDP
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        src, dst = eth.src, eth.dst
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(dst, ofp.OFPP_FLOOD)
        actions = []

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        is_game = ip_pkt is not None and (ip_pkt.tos >> 2) == 46
        if is_game:
            # Queue 1 is configured as the high-priority game queue.
            actions.append(parser.OFPActionSetQueue(1))

        actions.append(parser.OFPActionOutput(out_port))

        if out_port != ofp.OFPP_FLOOD:
            # Match DSCP for ALL IPv4 flows so a default flow cannot
            # shadow a later high-priority game flow for the same MACs.
            fields = dict(in_port=in_port, eth_src=src, eth_dst=dst,
                          eth_type=eth.ethertype)
            if ip_pkt is not None:
                fields["ip_dscp"] = ip_pkt.tos >> 2
            match = parser.OFPMatch(**fields)
            self.add_flow(datapath, 10, match, actions, msg.buffer_id)

        if msg.buffer_id == ofp.OFP_NO_BUFFER:
            data = msg.data
        else:
            data = None

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

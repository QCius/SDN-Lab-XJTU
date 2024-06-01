from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ether_types

ETHERNET = ethernet.ethernet.__name__
ETHERNET_MULTICAST = "ff:ff:ff:ff:ff:ff"
ARP = arp.arp.__name__


class Switch_Dict(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Switch_Dict, self).__init__(*args, **kwargs)
        self.sw = {} #(dpid, src_mac, dst_ip)=>in_port, you may use it in mission 2
        self.mac_to_port = {} # A global data structure to save the mapping
        

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        dp = datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=priority,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst)
        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        # the identity of switch
        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})
        # the port that receive the packet
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        if eth_pkt.ethertype == ether_types.ETH_TYPE_IPV6:
            return
        # get the mac
        dst = eth_pkt.dst
        src = eth_pkt.src
        # get protocols
        header_list = dict((p.protocol_name, p) for p in pkt.protocols if type(p) != str)
        if dst == ETHERNET_MULTICAST and ARP in header_list:
            # you need to code here to avoid broadcast loop to finish mission 2
            arp_packet = header_list[ARP]
            dst_ip = arp_packet.dst_ip
            if (dpid, src, dst_ip) in self.sw: 
                if self.sw[(dpid, src, dst_ip)] != in_port: # Received duplicate packets on different ports
                    # Add flow entry to drop ARP packet
                    match = parser.OFPMatch(eth_type = ether_types.ETH_TYPE_ARP, 
                        eth_src = src,
                        arp_tpa = arp_packet.dst_ip,
                        in_port = in_port)
                    actions = []
                    self.add_flow(dp, 1, match, actions, idle_timeout = 5, hard_timeout = 10) # Flow table has to update.
                    return
            else:
                self.sw[(dpid, src, dst_ip)] = in_port

        # self-learning
        # you need to code here to avoid the direct flooding 
        # having fun 
        # :)
        # just code in mission 1

        # Record the mapping relationship between src_mac to in_port
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]: 
            out_port = self.mac_to_port[dpid][dst]
        else: 
            out_port = ofp.OFPP_FLOOD 

        actions = [parser.OFPActionOutput(out_port)] 

        if out_port != ofp.OFPP_FLOOD: # Already learned, therefore sending flow table entries
            match = parser.OFPMatch(in_port = in_port, eth_src = src, eth_dst = dst)
            self.add_flow(dp, 1, match, actions)

        # Anyway, instruct the switch to send packets
        # Function parser.OFPPacketOut() does not involve the flow table, it just instructs the switch
        # to forward the packet to the specified port
        out = parser.OFPPacketOut(datapath = dp, buffer_id = msg.buffer_id,in_port = in_port,
            actions = actions, data = msg.data) 
        dp.send_msg(out)
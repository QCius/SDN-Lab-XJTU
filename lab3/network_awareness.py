from ryu.base import app_manager
from ryu.base.app_manager import lookup_service_brick
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.controller import ofp_event
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, arp
from ryu.lib import hub
from ryu.topology import event
from ryu.topology.api import get_host, get_link, get_switch
from ryu.topology.switches import LLDPPacket

import networkx as nx
import copy
import time
import struct

GET_TOPOLOGY_INTERVAL = 2
SEND_ECHO_REQUEST_INTERVAL = .05
GET_DELAY_INTERVAL = 2


class NetworkAwareness(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(NetworkAwareness, self).__init__(*args, **kwargs)
        self.switch_info = {}  # dpid: datapath
        self.link_info = {}  # (s1, s2): s1.port
        self.port_link={} # s1,port:s1,s2
        self.port_info = {}  # dpid: (ports linked hosts)
        self.topo_map = nx.Graph()
        self.topo_thread = hub.spawn(self._get_topology)

        self.switches = {}
        self.lldp_delay = {}
        self.echo_delay = {}
        self.weight = 'delay' # Specify the weight type to be used when calculating the shortest path


    def add_flow(self, datapath, priority, match, actions):
        dp = datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
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

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        dpid = dp.id

        if ev.state == MAIN_DISPATCHER:
            self.switch_info[dpid] = dp

        if ev.state == DEAD_DISPATCHER:
            del self.switch_info[dpid]
    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_hander(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        try:
            src_dpid, src_port_no = LLDPPacket.lldp_parse(msg.data)
            
            if not self.switches: # There was an issue with the originally provided code because it did not consider non-existent situations
                self.switches = lookup_service_brick('switches')

            for port in self.switches.ports.keys():
                if src_dpid == port.dpid and src_port_no == port.port_no:
                    #self.logger.info("lldp_delay_time_in_packetin=%.5f",self.switches.ports[port].delay)
                    self.lldp_delay[(src_dpid, dpid)] = self.switches.ports[port].delay
        except:
            #self.logger.info("Note: packet_in_hander exception")
            return
        
    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def echo_hander(self,ev):
        recv_time = time.time()
        #self.logger.info("recv_time=%.5f",recv_time)
        try:
            msg = ev.msg
            dpid = msg.datapath.id
            send_time = struct.unpack('d', msg.data)[0]
            #self.logger.info("send_time=%.5f",send_time)
            self.echo_delay[dpid] = recv_time - send_time
            #self.logger.info("delay_time_in_echohander=%.5f",self.echo_delay[dpid])
        except:
            #self.logger.info("note: echo_hander exception")
            return

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        self.logger.info("Note: Now in port_status_handle")
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        if msg.reason in [ofproto.OFPPR_ADD, ofproto.OFPPR_MODIFY]:
            datapath.ports[msg.desc.port_no] = msg.desc
            self.topo_map.clear() 
            # Delete information from relevant flow tables on all switches on the affected link
            for dpid in self.port_info.keys():
                for port in self.port_info[dpid]:
                     self.delete_flow(self.switch_info[dpid],port)

        elif msg.reason == ofproto.OFPPR_DELETE:
            datapath.ports.pop(msg.desc.port_no, None)
        else:
            return
        self.send_event_to_observers(ofp_event.EventOFPPortStateChange(
        datapath, msg.reason, msg.desc.port_no),
        datapath.state)

    def echo_send_requests(self, switch):
        datapath = switch.dp
        parser = datapath.ofproto_parser
        send_time = time.time()
        data = struct.pack('d', send_time)  # Encode float as an 8-byte string
        echo_req = parser.OFPEchoRequest(datapath, data = data)
        datapath.send_msg(echo_req)
        hub.sleep(0.2)
        return

    def delete_flow(self, datapath,port_no):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        try:
            match = parser.OFPMatch(in_port=port_no)
            flow_mod = parser.OFPFlowMod(datapath=datapath,command=ofproto.OFPFC_DELETE,out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,match=match)
            datapath.send_msg(flow_mod)
            self.logger.info("Deleted flow entries associated with port %s on switch %s", port_no, datapath.id)
        except Exception as e:
            self.logger.error("Failed to delete flow entries associated with port %s on switch %s: %s",
                port_no, datapath.id, str(e))

    def _get_topology(self):
        _hosts, _switches, _links = None, None, None
        while True:
            hosts = get_host(self)
            switches = get_switch(self)
            links = get_link(self)

            # update topo_map when topology change
            if [str(x) for x in hosts] == _hosts and [str(x) for x in switches] == _switches and [str(x) for x in links] == _links:
                continue
            _hosts, _switches, _links = [str(x) for x in hosts], [str(x) for x in switches], [str(x) for x in links]

            for switch in switches:
                self.port_info.setdefault(switch.dp.id, set())
                # record all ports
                for port in switch.ports:
                    self.port_info[switch.dp.id].add(port.port_no)
                self.echo_send_requests(switch)
            for host in hosts:
                # take one ipv4 address as host id
                if host.ipv4:
                    self.link_info[(host.port.dpid, host.ipv4[0])] = host.port.port_no
                    self.topo_map.add_edge(host.ipv4[0], host.port.dpid, hop=1, delay=0, is_host=True)
            for link in links:
                # delete ports linked switches
                self.port_info[link.src.dpid].discard(link.src.port_no)
                self.port_info[link.dst.dpid].discard(link.dst.port_no)

                # s1 -> s2: s1.port, s2 -> s1: s2.port
                self.port_link[(link.src.dpid,link.src.port_no)]=(link.src.dpid, link.dst.dpid)
                self.port_link[(link.dst.dpid,link.dst.port_no)] = (link.dst.dpid, link.src.dpid)

                self.link_info[(link.src.dpid, link.dst.dpid)] = link.src.port_no
                self.link_info[(link.dst.dpid, link.src.dpid)] = link.dst.port_no

                delay = self.calculate_link_delay(link.src.dpid, link.dst.dpid)
                self.logger.info("Added link: src_dpid=%s dst_dpid=%s delay= %.5fms",link.src.dpid, link.dst.dpid, delay*1000)
                self.topo_map.add_edge(link.src.dpid, link.dst.dpid, hop=1, delay=delay,is_host=False)

            if self.weight == 'delay':
                self.show_topo_map()
            hub.sleep(GET_TOPOLOGY_INTERVAL)

    def calculate_link_delay(self, src_dpid, dst_dpid):
        # This function should calculate the delay between two switches

        # If the specified key does not exist in the dictionary, the dict. get method
        # returns the default value of 0 and does not throw a KeyError exception
        lldp_delay_s12 = self.lldp_delay.get((src_dpid, dst_dpid), 0) 
        lldp_delay_s21 = self.lldp_delay.get((dst_dpid, src_dpid), 0)
        echo_delay_s1 = self.echo_delay.get(src_dpid, 0)
        echo_delay_s2 = self.echo_delay.get(dst_dpid, 0)
        delay = (lldp_delay_s12 + lldp_delay_s21 - echo_delay_s1 - echo_delay_s2) / 2
        return max(delay, 0)  # Ensure non-negative delay
   

    def shortest_path(self, src, dst, weight='delay'):
        try:
            paths = list(nx.shortest_simple_paths(self.topo_map, src, dst, weight=weight))
            return paths[0]
        except:
            self.logger.info('host not find/no path')

    def show_topo_map(self):
        self.logger.info('topo map:')
        self.logger.info('{:^10s}  ->  {:^10s}'.format('node', 'node'))
        for src, dst in self.topo_map.edges:
            self.logger.info('{:^10s}      {:^10s}'.format(str(src), str(dst)))
        self.logger.info('\n')


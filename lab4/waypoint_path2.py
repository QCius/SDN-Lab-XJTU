import requests
import json

def add_flow(dpid, src_ip, dst_ip, in_port, out_port, priority=10,mpls_tc=2):
    flow = {
        "dpid": dpid,
        "idle_timeout": 0,
        "hard_timeout": 0,
        "priority": priority,
        "match":{
            "dl_type": 2048,
            "in_port": in_port,
            "nw_src": src_ip,
            "nw_dst": dst_ip,
            #"dl_src": src_mac,
            #"dl_dst": dst_mac,
            "mpls_tc": mpls_tc 
        },
        "actions":[
            {
                "type":"OUTPUT",
                "port": out_port
            }
        ]
    }

    url = 'http://localhost:8080/stats/flowentry/add'
    ret = requests.post(
        url, headers={'Accept': 'application/json'}, data=json.dumps(flow))
    print(ret)

def show_path(src, dst, port_path):
    print('install mywaypoint path: {} -> {}'.format(src, dst))
    path = str(src) + ' -> '
    for node in port_path:
        path += '{}:s{}:{}'.format(*node) + ' -> '
    path += str(dst)
    path += '\n'
    print(path)

def install_path():
    '23 -> 4:s22:2 -> 2:s9:3 -> 3:s16:2 -> 3:s7:2 -> 3:25:2 -> 1'
    src_sw, dst_sw = 23, 1
    waypoint_sw = 9  # Tinker 10.0.0.21, s9

    path = [(4, 22, 2), (2, 9, 3), (3, 16, 2), (3, 7, 2), (3, 25, 2)]
    # path = [(3, 7 , 2)]
    #MIT_mac="00:00:00:00:00:01"
    #SDC_mac="00:00:00:00:00:02"
    # send flow mod
    for node in path:
        in_port, dpid, out_port = node
        add_flow(dpid, '10.0.0.0/8', '10.0.0.0/8', in_port, out_port)
        add_flow(dpid, '10.0.0.0/8', '10.0.0.0/8', out_port, in_port)
        #add_flow(dpid, '10.0.0.0/8', '10.0.0.0/8', in_port, out_port,SDC_mac,MIT_mac)
        #add_flow(dpid, '10.0.0.0/8', '10.0.0.0/8', out_port, in_port,MIT_mac,SDC_mac)
    show_path(src_sw, dst_sw, path)

if __name__ == '__main__':
    install_path()

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel


core_switchs = []
aggr_switchs =  [[] for _ in range(8)] # 8 is redundant
edge_switchs =[[] for _ in range(8)]
hosts = [[] for _ in range(8)]
core_switch_num = 4
pod_num = 4
pod_switch_ae_num = 2
pod_host_num = 4

class fatTree(Topo):
    def build(self):

        # Core switch
        for i in range(core_switch_num):
            core_switch = self.addSwitch("core"+str(i))
            core_switchs.append(core_switch)
        # Aggregation pods
        for i in range(pod_num):
            for j in range(pod_switch_ae_num):
                aggr_switch = self.addSwitch("Arpod"+str(i)+"no"+str(j))
                aggr_switchs[i].append(aggr_switch) 
        # Edge pods
        for i in range(pod_num):
            for j in range(pod_switch_ae_num):
                edge_switch = self.addSwitch("Edpod"+str(i)+"no"+str(j))
                edge_switchs[i].append(edge_switch)
        # Hosts
        for i in range(pod_num):
            for j in range(pod_host_num):
                host= self.addHost("h"+str(i)+"_"+str(j))
                hosts[i].append(host)

        # Core links
        for i in range(2):
            for j in range(4):
                self.addLink(core_switchs[i],aggr_switchs[j][0])
        for i in range(2,4):
            for j in range(4):
                self.addLink(core_switchs[i],aggr_switchs[j][1])
        # Switch links
        for i in range(4):
            self.addLink(aggr_switchs[i][0],edge_switchs[i][0])
            self.addLink(aggr_switchs[i][0],edge_switchs[i][1])
            self.addLink(aggr_switchs[i][1],edge_switchs[i][0])
            self.addLink(aggr_switchs[i][1],edge_switchs[i][1])
        # Host links
        for i in range(4):
            self.addLink(edge_switchs[i][0],hosts[i][0])
            self.addLink(edge_switchs[i][0],hosts[i][1])
            self.addLink(edge_switchs[i][1],hosts[i][2])
            self.addLink(edge_switchs[i][1],hosts[i][3])

def run():
    topo = fatTree()
    net = Mininet(topo,controller=None) 
    net.start()
    CLI(net)
    net.stop()
    
if __name__ == '__main__':
    setLogLevel('info') # output, info, debug
    run()

# sudo python fattree.py
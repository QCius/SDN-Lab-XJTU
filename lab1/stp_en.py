import os

def run():
    core_switch_num = 4
    pod_num = 4
    pod_switch_ae_num = 2
    for i in range(core_switch_num):
        os.system("sudo ovs-vsctl set Bridge core"+ str(i) + " stp_enable=true")
        os.system("sudo ovs-vsctl del-fail-mode core"+str(i))
    for i in range(pod_num):
        for j in range(pod_switch_ae_num):
            os.system("sudo ovs-vsctl set Bridge Arpod"+ str(i) +"no"+str(j)+ " stp_enable=true")
            os.system("sudo ovs-vsctl del-fail-mode Arpod"+ str(i) +"no"+str(j))
            os.system("sudo ovs-vsctl set Bridge Edpod"+ str(i) +"no"+str(j)+ " stp_enable=true")
            os.system("sudo ovs-vsctl del-fail-mode Edpod"+ str(i) +"no"+str(j))

if __name__ == '__main__':
    run()
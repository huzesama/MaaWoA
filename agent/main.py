import sys
from maa.agent.agent_server import AgentServer
from maa.tasker import Tasker

import crewUsedCompare
import dailyUniqueCompare
import swipe_inBoxByVector
import airlineCardListColorMatch
import roiManager

def main():  
    socket_id = sys.argv[-1]  
    AgentServer.start_up(socket_id)  
    AgentServer.join()  
    AgentServer.shut_down()  
  
if __name__ == "__main__":  
    main()
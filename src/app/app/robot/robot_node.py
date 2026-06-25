import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from main_task import main_task
import DR_init
from interfaces.action import RobotTask
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

from rclpy.node import Node
from rclpy.action import ActionServer

class RobotNode(Node):
    def __init__(self):
        super().__init__("my_node")

        self.action_server = ActionServer(
            self,
            RobotTask,
            "fibonacci",
            self.execute_callback
        )

    def execute_callback(self, goal_handle):
        result = main_task(goal_handle)
        if result.succeed:
            goal_handle.succeed()

            return result
        else:
            return result


def main():

    rclpy.init()

    node = RobotNode()
    DR_init.__dsr__node = node

    rclpy.spin(node)

    node.destroy_node()

    rclpy.shutdown()



if __name__ == '__main__':
    main()

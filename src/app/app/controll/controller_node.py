import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient


import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from std_msgs.msg import String
from example_interfaces.srv import AddTwoInts, SetBool, Trigger
from example_interfaces.action import Fibonacci

from db import BookDatabaseManager
from interfaces.msg import AnomalyDetection
from interfaces.srv import StartClear, RequestQR, ResetDetection
from interfaces.action import RobotTask

class ControllerNode(Node):
    def __init__(self):
        super().__init__("controller_node")

        self.db_manager = BookDatabaseManager()


def main():
    rclpy.init()

    node = ControllerNode()
    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
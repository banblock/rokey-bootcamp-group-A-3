from rclpy.node import Node
from std_msgs.msg import String
from example_interfaces.srv import Trigger, SetBool
import rclpy
from interfaces.msg import AnomalyDetection
from interfaces.srv import RequestQR, ResetDetection
class VisionNode(Node):
    def __init__(self):
        super().__init__("my_node")

        self.pub_anomaly = self.create_publisher(
            AnomalyDetection,
            "anomaly",
            10
        )

        # Service Server (1)
        self.response_qr = self.create_service(
            RequestQR,
            "qr",
            self.qr_callback
        )

        self.response_reset = self.create_service(
            ResetDetection,
            "reset",
            self.reset_callback
        )


    def topic_callback(self, msg):
        print(msg.data)

    def qr_callback(self, request, response):
        
        return response

    def reset_callback(self, request, response):
        response.success = True
        response.message = "Reset"
        return response
    
def main():
    rclpy.init()

    node = VisionNode()
    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
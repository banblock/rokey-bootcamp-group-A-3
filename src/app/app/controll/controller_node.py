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
        super().__init__("my_node")

        self.db_manager = BookDatabaseManager()
        #------------ 주는 곳 -----------------

        # Service Server (1)
        self.clear_srv = self.create_service(
            StartClear,
            "add",
            self.add_callback
        )

        #---------------------- 받는곳 ------------------

        # Service Client (1)
        self.request_qr = self.create_client(
            RequestQR,
            "service1"
        )

        self.reset_detection = self.create_client(
            ResetDetection,
            "service2"
        )

        # Action Client (1)
        self.action_client = ActionClient(
            self,
            RobotTask,
            "fibonacci"
        )
        self.goal_handle = None
        # Subscriptions

        self.vision_exception_subs = self.create_subscription(
            AnomalyDetection,
            "topic",
            self.anomaly_detection_callback,
            10
        )
    
    # sub callback
    def anomaly_detection_callback(self, msg):
        pass
    # -----------------------------
    # Service callbacks
    # -----------------------------

    def clear_callback(self, request, response):
        response.sum = request.a + request.b
        return response

    def bool_callback(self, request, response):
        response.success = True
        response.message = "OK"
        return response

    def trigger_callback(self, request, response):
        response.success = True
        response.message = "Done"
        return response

    # action request
    def send_goal(self, booksession):
        goal = RobotTask.Goal()
        goal.booksession = booksession

        future = self.action_client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback
        )

        future.add_done_callback(self.goal_response_callback)
    
    def goal_response_callback(self, future):
        self.goal_handle = future.result()

        if not self.goal_handle.accepted:
            print("Goal rejected")
            return

        print("Goal accepted")

        result_future = self.goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    # 3. Feedback 수신
    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.state
        if feedback == 1:
            self.cancel_goal()
        print(feedback.progress)

    # 4. Result 수신
    def result_callback(self, future):
        result = future.result().result
        print(result.success)

    # 5. Cancel 요청
    def cancel_goal(self):
        if self.goal_handle is None:
            print("No goal")
            return

        future = self.goal_handle.cancel_goal_async()
        future.add_done_callback(self.cancel_callback)

    # 6. Cancel 결과
    def cancel_callback(self, future):
        cancel_response = future.result()

        if len(cancel_response.goals_canceling) > 0:
            print("Cancel accepted")
        else:
            print("Cancel rejected")

def main():
    rclpy.init()

    node = ControllerNode()
    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
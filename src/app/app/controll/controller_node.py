import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient


class TestActionClient(Node):

    def __init__(self):
        super().__init__('test_action_client')

        self._action_client = ActionClient(
            self,
            Action,
            '/test_action'
        )

    def send_goal(self, target):

        goal_msg = Action.Goal()
        goal_msg.target = target

        self._action_client.wait_for_server()

        future = self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )

        future.add_done_callback(
            self.goal_response_callback
        )

    def goal_response_callback(self, future):

        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().info(
                'Goal Rejected'
            )
            return

        self.get_logger().info(
            'Goal Accepted'
        )

        result_future = (
            goal_handle.get_result_async()
        )

        result_future.add_done_callback(
            self.result_callback
        )

    def feedback_callback(self, feedback_msg):

        feedback = feedback_msg.feedback

        self.get_logger().info(
            f'Progress: {feedback.progress}'
        )

    def result_callback(self, future):

        result = future.result().result

        self.get_logger().info(
            f'Success: {result.success}'
        )

        rclpy.shutdown()


def main():

    rclpy.init()

    node = TestActionClient()

    node.send_goal(100)

    rclpy.spin(node)


if __name__ == '__main__':
    main()
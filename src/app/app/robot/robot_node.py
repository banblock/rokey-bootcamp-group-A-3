import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer

class RobotActionSever(Node):
    def __init__(self):
        super().__init__('fibonacci_action_server')

        self._action_server = ActionServer(
            self,
            Action,
            'fibonacci',
            self.execute_callback
        )

        self.get_logger().info('Fibonacci Action Server started')

    def execute_callback(self, goal_handle):
        self.get_logger().info('Action goal received')

        order = goal_handle.request.order

        feedback_msg = Action.Feedback()
        feedback_msg.sequence = [0, 1]

        for i in range(2, order):
            feedback_msg.sequence.append(
                feedback_msg.sequence[i - 1] + feedback_msg.sequence[i - 2]
            )

            self.get_logger().info(f'Feedback: {feedback_msg.sequence}')
            goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()

        result = Actoin.Result()
        result.sequence = feedback_msg.sequence

        self.get_logger().info('Action goal succeeded')

        return result

def main(args=None):
    rclpy.init(args=args)

    node = RobotActionSever()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

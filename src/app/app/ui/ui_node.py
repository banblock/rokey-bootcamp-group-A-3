import rclpy
from rclpy.node import Node
from interfaces.srv import StartClear
class UINode(Node):
    def __init__(self):
        super().__init__("my_node")

        # Service Client 1
        self.cli1 = self.create_client(
            StartClear,
            "start_clear"
        )

    # service 요청 메서드 (내용 만 가져가서 따로 만들어도 됨)
    def clear_start(self):
        req = StartClear.Request()

        future = self.client.call_async(req)

        rclpy.spin_until_future_complete(self, future)

        return future.result()


# def main(args=None):
#     rclpy.init(args=args)

#     node = UINode()
#     rclpy.spin(node)

#     node.destroy_node()
#     rclpy.shutdown()


# if __name__ == "__main__":
#     main()
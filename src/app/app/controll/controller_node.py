import rclpy
from rclpy.node import Node
import time
import rclpy
from rclpy.node import Node
from dsr_msgs2.srv import DrlStart, DrlPause, DrlResume, DrlStop, GetDrlState
from app.robot import main_task
# from app.db import BookDatabaseManager


class ControllerNode(Node):
    def __init__(self):
        super().__init__("controller_node")

        # self.db_manager = BookDatabaseManager()

        self.rqt_drl_start = self.create_client(
            DrlStart,
            "/dsr01/drl/drl_start"
        )

        while not self.rqt_drl_start.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for service...')
        
        self.start_code(0)

        time.sleep(10)

        self.request_pause = self.create_client(
            DrlPause,
            '/dsr01/drl/drl_pause'
        )
        while not self.request_pause.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for service...')
        
        self.pause_code()

        time.sleep(5)

        self.request_resume = self.create_client(
            DrlResume,
            '/dsr01/drl/drl_resume'
        )
        while not self.request_resume.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for service...')

        self.resume_code()

        # time.sleep(20)

        self.request_stop = self.create_client(
            DrlStop,
            '/dsr01/drl/drl_stop'
        )
        while not self.request_stop.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for service...')

        # self.stop_code()
        

        self.clear_response_server = self.create_service(

        ) 


        self.request_Qr = self.create_client(

        )
        while not self.request_Qr.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for service...')
        
        self.vision_anomaly_subs = self.create_subscription()
        self.request_reset_vision = self.create_client()
        self.request_reset_UI = self.create_client()
        
    def start_code(self, session):
        req = DrlStart.Request()
        code = main_task.main_task
        sys = 0
        req.robot_system = sys
        req.code = f"session = {session}" + code

        future = self.rqt_drl_start.call_async(req)
        future.add_done_callback(self.response_callback)
    
    def pause_code(self):
        req = DrlPause.Request()

        future = self.request_pause.call_async(req)
        future.add_done_callback(self.response_callback)

    def resume_code(self):
        req = DrlResume.Request()

        future = self.request_resume.call_async(req)
        future.add_done_callback(self.response_callback)
    
    def stop_code(self):
        req = DrlStop.Request()
        req.stop_mode = 1
        future = self.request_stop.call_async(req)
        future.add_done_callback(self.response_callback)

    def response_callback(self, future):
        response = future.result()
        self.get_logger().info(f"Result: {response.success}")


def main():
    rclpy.init()

    node = ControllerNode()
    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

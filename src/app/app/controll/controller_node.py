import rclpy
from rclpy.node import Node
from enum import Enum, auto

from std_srvs.srv import Empty, Trigger
from std_msgs.msg import Bool
from app.db import db_manager
from dsr_msgs2.srv import (
    DrlStart,
    DrlPause,
    DrlResume,
    DrlStop,
    GetDrlState,
    GetRobotState,
    SetRobotMode,
    GetLastAlarm,
)

from interfaces.srv import UiErrorResponse, UiErrorNotify
from app.robot import main_task


ROBOT_NS = "/dsr01"

ROBOT_SYSTEM_REAL = 0
ROBOT_MODE_AUTONOMOUS = 1

DRL_PLAY = 0
DRL_STOP = 1
DRL_HOLD = 2

UI_RESTART = 0
UI_MANUAL_CONTROL = 1
UI_RESET_TASK = 2

ERR_ENTRY_POINT_OBSTACLE = 0
ERR_ROBOT_SAFE_STOP = 1
ERR_TASK_COLLISION_OR_MISS = 2
ERR_EMERGENCY_STOP = 3
ERR_DATA_NOT_FOUND = 4
ERR_SYS_FAIL = 5

STATE_SAFE_OFF = 3
STATE_SAFE_STOP = 5
STATE_EMERGENCY_STOP = 6
STATE_RECOVERY = 8
STATE_SAFE_STOP2 = 9
STATE_SAFE_OFF2 = 10
STATE_NOT_READY = 15


class ControllerState(Enum):
    IDLE = auto()
    QR_REQUESTED = auto()
    TASK_RUNNING = auto()
    PAUSED_BY_ERROR = auto()
    WAITING_UI_RESPONSE = auto()
    RESETTING = auto()
    ERROR = auto()


class ControllerNode(Node):
    def __init__(self):
        super().__init__("controller_node")

        self.state = ControllerState.IDLE
        self.current_session = 0
        self.current_error_code = None
        self.db_manager = db_manager.BookDatabaseManager()

        #dsr 추적여부
        self.dsr_polling_enabled = False
        self.pending_drl_state = False
        self.pending_robot_state = False

        #drl client
        self.drl_start_cli = self.create_client(DrlStart, f"{ROBOT_NS}/drl/drl_start")
        self.drl_pause_cli = self.create_client(DrlPause, f"{ROBOT_NS}/drl/drl_pause")
        self.drl_resume_cli = self.create_client(DrlResume, f"{ROBOT_NS}/drl/drl_resume")
        self.drl_stop_cli = self.create_client(DrlStop, f"{ROBOT_NS}/drl/drl_stop")
        self.get_drl_state_cli = self.create_client(GetDrlState, f"{ROBOT_NS}/drl/get_drl_state")
        
        #robot state
        self.get_robot_state_cli = self.create_client(GetRobotState, f"{ROBOT_NS}/system/get_robot_state")
        self.set_robot_mode_cli = self.create_client(SetRobotMode, f"{ROBOT_NS}/system/set_robot_mode")
        self.get_last_alarm_cli = self.create_client(GetLastAlarm, f"{ROBOT_NS}/system/get_last_alarm")

        # self.wait_for_dsr_services()

        # UI -> Controller
        self.create_service(Empty, "/controller/cleanup_request", self.handle_cleanup_request)
        self.create_service(UiErrorResponse, "/controller/error_response", self.handle_ui_error_response)

        # Controller -> UI
        self.ui_error_notify_cli = self.create_client(UiErrorNotify, "/ui/error_notify")
        self.ui_task_complete_cli = self.create_client(Trigger, "/ui/task_complite")

        # Controller -> Vision
        self.vision_qr_cli = self.create_client(Trigger, "/vision/scan_qr")

        self.wait_for_ui_qr_services()
        self.test_cli()
        # Vision -> Controller
        self.create_subscription(Bool, "/vision/emergency_stop", self.handle_entry_obstacle, 10)

        # state check loop
        self.monitor_timer = self.create_timer(0.5, self.poll_dsr_state)

        self.get_logger().info("ControllerNode ready.")

    def wait_for_dsr_services(self):
        clients = [
            self.drl_start_cli,
            self.drl_pause_cli,
            self.drl_resume_cli,
            self.drl_stop_cli,
            self.get_drl_state_cli,
            self.get_robot_state_cli,
            self.set_robot_mode_cli,
            self.get_last_alarm_cli,
        ]

        for cli in clients:
            while not cli.wait_for_service(timeout_sec=1.0):
                self.get_logger().info(f"Waiting for service: {cli.srv_name}")
        
    def wait_for_ui_qr_services(self):
        clients = [
            self.ui_error_notify_cli,
            self.vision_qr_cli
        ]

        for cli in clients:
            while not cli.wait_for_service(timeout_sec=1.0):
                self.get_logger().info(f"Waiting for service: {cli.srv_name}")

    # =========================
    # UI 요청
    # =========================

    def handle_cleanup_request(self, request, response):
        if self.state != ControllerState.IDLE:
            self.get_logger().warn(f"Cleanup rejected. state={self.state.name}")
            return response

        self.get_logger().info("Cleanup request received.")
        self.state = ControllerState.QR_REQUESTED
        self.request_qr()
        return response

    def handle_ui_error_response(self, request, response):
        code = request.code
        if self.state != ControllerState.WAITING_UI_RESPONSE:
            response.success = False
            response.message = f"Not waiting UI response. state={self.state.name}"
            return response

        if code == UI_RESTART:
            self.get_logger().info("UI selected RESTART.")
            self.resume_drl()
            response.success = True
            response.message = "Restart accepted."
            return response

        if code == UI_MANUAL_CONTROL:
            self.get_logger().info("UI selected MANUAL_CONTROL.")
            self.dsr_polling_enabled = False
            response.success = True
            response.message = "Manual control accepted. Waiting reset request later."
            return response

        if code == UI_RESET_TASK:
            self.get_logger().info("UI selected RESET_TASK.")
            self.reset_task()
            response.success = True
            response.message = "Reset accepted."
            return response

        response.success = False
        response.message = f"Unknown response code: {code}"
        return response

    # =========================
    # Vision 신호
    # =========================

    def handle_entry_obstacle(self, msg):
        if not msg.data:
            return

        if self.state != ControllerState.TASK_RUNNING:
            return

        self.pause_and_notify(ERR_ENTRY_POINT_OBSTACLE, "엔트리포인트 이물질 감지")

    # def handle_vision_anomaly(self, msg):
        if not msg.data:
            return

        if self.state != ControllerState.TASK_RUNNING:
            return

        self.pause_and_notify(ERR_TASK_COLLISION_OR_MISS, "테스크 진행 중 걸림, 충돌, 놓침")

    # =========================
    # Main flow
    # =========================

    def request_qr(self):
        if not self.vision_qr_cli.service_is_ready():
            self.notify_ui_error(ERR_SYS_FAIL, "Vision QR service not ready")
            self.state = ControllerState.ERROR
            return

        future = self.vision_qr_cli.call_async(Trigger.Request())
        future.add_done_callback(self.on_qr_response)

    def on_qr_response(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(ERR_SYS_FAIL, f"QR request failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(ERR_SYS_FAIL, res.message)
            self.state = ControllerState.ERROR
            return

        if res.message == "None":
            self.finish_all_tasks()
            return
        
        # 수정 필요. db 참조 session 가져오기
        try:
            book_data = self.db_manager.get_book_by_qr(res.message)
        except Exception as e:
            self.notify_ui_error(ERR_DATA_NOT_FOUND, res.message)
            self.state = ControllerState.ERROR
            return
        
        
        self.current_session = book_data["target_location"]

        self.start_drl(self.current_session)

    def start_drl(self, session):
        req = DrlStart.Request()
        req.robot_system = ROBOT_SYSTEM_REAL
        req.code = f"session = {session}\n" + main_task.main_task

        future = self.drl_start_cli.call_async(req)
        future.add_done_callback(self.on_drl_start)

    def on_drl_start(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(ERR_SYS_FAIL, f"DRL start failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(ERR_SYS_FAIL, "DRL start rejected")
            self.state = ControllerState.ERROR
            return

        self.state = ControllerState.TASK_RUNNING
        self.dsr_polling_enabled = True
        self.get_logger().info("DRL task started.")

    # =========================
    # DSR pause / resume / stop
    # =========================

    def pause_and_notify(self, error_code, message):
        self.current_error_code = error_code
        self.state = ControllerState.PAUSED_BY_ERROR

        future = self.drl_pause_cli.call_async(DrlPause.Request())
        future.add_done_callback(lambda f: self.on_pause_done(f, error_code, message))

    def on_pause_done(self, future, error_code, message):
        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(error_code, f"Pause failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(error_code, "Pause rejected")
            self.state = ControllerState.ERROR
            return

        self.dsr_polling_enabled = False
        self.state = ControllerState.WAITING_UI_RESPONSE
        self.notify_ui_error(error_code, message)

    def resume_drl(self):
        future = self.drl_resume_cli.call_async(DrlResume.Request())
        future.add_done_callback(self.on_resume_done)

    def on_resume_done(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(ERR_SYS_FAIL, f"Resume failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(ERR_SYS_FAIL, "Resume rejected")
            self.state = ControllerState.ERROR
            return

        self.state = ControllerState.TASK_RUNNING
        self.dsr_polling_enabled = True
        self.get_logger().info("DRL resumed.")

    def stop_drl(self):
        req = DrlStop.Request()
        req.stop_mode = 1

        future = self.drl_stop_cli.call_async(req)
        future.add_done_callback(self.on_stop_done)

    def on_stop_done(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.get_logger().error(f"DRL stop failed: {e}")
            return

        if not res.success:
            self.get_logger().error("DRL stop rejected.")
            return

        self.get_logger().info("DRL stopped.")

    # =========================
    # DSR service polling
    # =========================

    def poll_dsr_state(self):
        if not self.dsr_polling_enabled:
            return

        if self.state != ControllerState.TASK_RUNNING:
            return

        if not self.pending_drl_state:
            self.pending_drl_state = True
            future = self.get_drl_state_cli.call_async(GetDrlState.Request())
            future.add_done_callback(self.on_drl_state)

        if not self.pending_robot_state:
            self.pending_robot_state = True
            future = self.get_robot_state_cli.call_async(GetRobotState.Request())
            future.add_done_callback(self.on_robot_state)

    def on_drl_state(self, future):
        self.pending_drl_state = False

        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(ERR_SYS_FAIL, f"GetDrlState failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(ERR_SYS_FAIL, "GetDrlState rejected")
            self.state = ControllerState.ERROR
            return

        if res.drl_state == DRL_STOP and self.state == ControllerState.TASK_RUNNING:
            self.on_task_complete()

        elif res.drl_state == DRL_HOLD and self.state == ControllerState.TASK_RUNNING:
            self.notify_ui_error(ERR_TASK_COLLISION_OR_MISS, "DRL HOLD state")
            self.state = ControllerState.WAITING_UI_RESPONSE
            self.dsr_polling_enabled = False

    def on_robot_state(self, future):
        self.pending_robot_state = False

        try:
            res = future.result()
        except Exception as e:
            self.notify_ui_error(ERR_ROBOT_SAFE_STOP, f"GetRobotState failed: {e}")
            self.state = ControllerState.ERROR
            return

        if not res.success:
            self.notify_ui_error(ERR_ROBOT_SAFE_STOP, "GetRobotState rejected")
            self.state = ControllerState.ERROR
            return

        robot_state = res.robot_state

        if robot_state == STATE_EMERGENCY_STOP:
            self.handle_robot_stop_error(ERR_EMERGENCY_STOP, "비상정지버튼")

        elif robot_state in (
            STATE_SAFE_OFF,
            STATE_SAFE_STOP,
            STATE_RECOVERY,
            STATE_SAFE_STOP2,
            STATE_SAFE_OFF2,
            STATE_NOT_READY,
        ):
            self.handle_robot_stop_error(ERR_ROBOT_SAFE_STOP, "로봇 안전정지상태 돌입")

    def handle_robot_stop_error(self, error_code, message):
        self.dsr_polling_enabled = False
        self.state = ControllerState.WAITING_UI_RESPONSE
        self.current_error_code = error_code

        self.request_last_alarm()
        self.notify_ui_error(error_code, message)

    def request_last_alarm(self):
        future = self.get_last_alarm_cli.call_async(GetLastAlarm.Request())
        future.add_done_callback(self.on_last_alarm)

    def on_last_alarm(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.get_logger().error(f"GetLastAlarm failed: {e}")
            return

        if res.success:
            alarm = res.log_alarm
            self.get_logger().error(
                f"LastAlarm level={alarm.level}, group={alarm.group}, "
                f"index={alarm.index}, param={alarm.param}"
            )

    # =========================
    # 완료 / 초기화
    # =========================

    def on_task_complete(self):
        self.dsr_polling_enabled = False

        self.get_logger().info("One DRL task completed. Request next QR.")

        self.state = ControllerState.QR_REQUESTED
        self.request_qr()

    def reset_task(self):
        self.state = ControllerState.RESETTING
        self.dsr_polling_enabled = False

        self.stop_drl()
        self.set_robot_autonomous_mode()

        self.state = ControllerState.IDLE

    def set_robot_autonomous_mode(self):
        req = SetRobotMode.Request()
        req.robot_mode = ROBOT_MODE_AUTONOMOUS

        future = self.set_robot_mode_cli.call_async(req)
        future.add_done_callback(self.on_set_robot_mode)

    def on_set_robot_mode(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.get_logger().error(f"SetRobotMode failed: {e}")
            return

        if res.success:
            self.get_logger().info("Robot mode set to AUTONOMOUS.")
        else:
            self.get_logger().error("SetRobotMode rejected.")

    def finish_all_tasks(self):
        self.dsr_polling_enabled = False
        self.state = ControllerState.IDLE

        self.request_ui_reset()

        self.get_logger().info("All cleanup tasks completed.")

    # =========================
    # UI / Vision 요청
    # =========================

    def notify_ui_error(self, code, message):
        self.get_logger().error(f"Notify UI error: code={code}, message={message}")

        if not self.ui_error_notify_cli.service_is_ready():
            self.get_logger().error("UI error notify service is not ready.")
            return

        req = UiErrorNotify.Request()
        req.code = code
        # req.message = message

        future = self.ui_error_notify_cli.call_async(req)
        future.add_done_callback(self.on_ui_notify_done)

    def on_ui_notify_done(self, future):
        try:
            res = future.result()
        except Exception as e:
            self.get_logger().error(f"UI notify failed: {e}")
            return

        if not res.success:
            self.get_logger().error(f"UI notify rejected: {res.message}")
    
    def request_ui_reset(self):

        if not self.ui_task_complete_cli.service_is_ready():
            self.get_logger().error("UI error notify service is not ready.")
            return
        future = self.ui_task_complete_cli.call_async(Trigger.Request())
        future.add_done_callback(self.on_ui_notify_done)


    #test code
    # def test_cli(self):
    #     #qr
    #     # if not self.vision_qr_cli.service_is_ready():
    #     #     self.notify_ui_error(ERR_DATA_NOT_FOUND, "Vision QR service not ready")
    #     #     self.state = ControllerState.ERROR
    #     #     return

    #     # future_qr = self.vision_qr_cli.call_async(Trigger.Request())
    #     # print(future_qr.message)

    #     #ui
    #     self.notify_ui_error(ERR_SYS_FAIL, "GetRobotState rejected")


        
def main():
    rclpy.init()
    node = ControllerNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
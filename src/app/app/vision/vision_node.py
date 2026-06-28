import os

# OpenCV가 Qt 기반 imshow 창을 만들 때 Wayland/Gnome 환경에서 죽는 경우를 줄이기 위한 설정.
# 반드시 main_vision 또는 cv2 import보다 먼저 설정되어야 한다.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("QT_QPA_FONTDIR", "/usr/share/fonts/truetype/dejavu")

import json
import time

import cv2
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from app.vision.main_vision import BookVision


CAMERA_INDEX = 3
FRAME_RATE = 30.0
QR_SCAN_TIMEOUT_SEC = 10.0


class BookVisionRosBridge(Node):
    """
    ROS 통신 담당 노드.

    최종 통신 구조:
    - Controller -> Vision : /vision/scan_qr 서비스 호출
      요청 의미: 카메라를 켜고 QR 인식을 시작한 뒤, 성공하면 QR 문자열을 서비스 응답으로 반환한다.
    - Vision -> Controller : /vision/emergency_stop 토픽 publish
      의미: QR 인식 성공 후 이물질 감시 중 알람이 발생하면 True를 보낸다.

    주의:
    - 이 파일은 main_vision.py를 subprocess로 실행하지 않는다.
    - main_vision.py의 BookVision 클래스를 import해서 ROS service/topic과 연결한다.
    - /vision/scan_qr 서비스가 호출되기 전까지 BookVision을 만들지 않으므로 카메라도 열리지 않는다.
    """

    def __init__(self):
        super().__init__("book_vision_ros_bridge")

        self.vision = None

        # scan_qr 서비스 콜백 안에서 QR을 찾는 중인지 여부
        self.scan_running = False

        # QR 인식 성공 후 이물질 감시를 계속할지 여부
        self.monitoring_active = False

        # QR 성공 콜백에서 채워지고, scan_qr 서비스 응답으로 반환된다.
        self.latest_qr_data = None
        self.latest_qr_payload = None

        # emergency_stop 토픽 중복 publish 방지용
        self.last_emergency_stop = False

        # Controller -> Vision: QR 인식 시작 + QR 결과 반환
        self.scan_qr_service = self.create_service(
            Trigger,
            "/vision/scan_qr",
            self.scan_qr_callback,
        )

        # Vision -> Controller: 이물질 알람 기반 비상정지 요청
        self.emergency_stop_publisher = self.create_publisher(
            Bool,
            "/vision/emergency_stop",
            10,
        )

        # 선택 사항: 상태 로그를 컨트롤러/UI에서 보고 싶을 때 사용
        self.status_publisher = self.create_publisher(
            String,
            "/vision/status",
            10,
        )

        # QR 인식 성공 이후에는 이 timer가 계속 프레임을 처리하면서 이물질 감시를 수행한다.
        # scan_qr 서비스 콜백이 QR을 찾는 동안에는 timer가 별도로 프레임을 처리하지 않는다.
        self.camera_timer = self.create_timer(
            1.0 / FRAME_RATE,
            self.camera_timer_callback,
        )

        self.get_logger().info(
            "비전 ROS bridge 시작: /vision/scan_qr 서비스 요청 대기 중"
        )

    def create_vision_if_needed(self):
        """scan_qr 서비스 요청을 받은 뒤에만 BookVision을 생성한다."""
        if self.vision is not None:
            return True

        self.get_logger().info("BookVision 생성 및 카메라 초기화 시작")

        self.vision = BookVision(
            camera_index=CAMERA_INDEX,
            on_qr_confirmed=self.qr_confirmed_callback,
            on_status=self.status_callback,
            on_stop_required=self.emergency_stop_callback,
            on_frame=None,  # main_vision.py 직접 실행과 동일하게 cv2.imshow 사용
        )

        if not self.vision.camera.is_opened():
            self.get_logger().error("카메라를 열 수 없습니다.")
            self.vision.close()
            self.vision = None
            return False

        return True

    def scan_qr_callback(self, request, response):
        """
        Controller가 호출하는 QR 인식 서비스.

        호출 예:
        ros2 service call /vision/scan_qr std_srvs/srv/Trigger "{}"

        응답:
        - success=True,  message=<QR 문자열>
        - success=False, message=<실패 원인>
        """
        if self.scan_running:
            response.success = False
            response.message = "QR scan is already running"
            return response

        if not self.create_vision_if_needed():
            response.success = False
            response.message = "Camera open failed"
            return response

        self.scan_running = True
        self.monitoring_active = False
        self.latest_qr_data = None
        self.latest_qr_payload = None
        self.last_emergency_stop = False

        # QR 인식 상태로 초기화한다.
        # QR 성공 후에는 BookVision 내부에서 자동으로 QR 감지를 멈추고 이물질 감시 상태로 전환된다.
        self.vision.resume_scan()

        self.get_logger().info(
            f"/vision/scan_qr 요청 수신: QR 인식 시작, timeout={QR_SCAN_TIMEOUT_SEC:.1f}s"
        )

        start_time = time.monotonic()

        while rclpy.ok():
            elapsed = time.monotonic() - start_time
            if elapsed >= QR_SCAN_TIMEOUT_SEC:
                self.scan_running = False
                self.monitoring_active = False
                response.success = True
                response.message = "QR_NOT_FOUND"
                self.get_logger().warning("QR 인식 timeout: QR_NOT_FOUND")
                return response

            if self.vision is None or not self.vision.camera.is_opened():
                self.scan_running = False
                self.monitoring_active = False
                response.success = True
                response.message = "CAMERA_ERROR"
                self.get_logger().error("QR 인식 중 카메라 오류")
                return response

            success, frame = self.vision.camera.read()
            if not success:
                continue

            self.vision.last_frame_time = time.monotonic()
            self.vision.process_frame(frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                self.stop_vision()
                self.scan_running = False
                self.monitoring_active = False
                response.success = True
                response.message = "USER_CANCELLED"
                return response

            if key == ord("d"):
                self.vision.toggle_debug_masks()

            # main_vision.py의 confirm_qr() -> qr_confirmed_callback()에서 값이 채워진다.
            if self.latest_qr_data is not None:
                qr_data = str(self.latest_qr_data)

                self.scan_running = False
                self.monitoring_active = True

                response.success = True
                response.message = qr_data

                self.get_logger().info(
                    f"QR 인식 성공: service response로 반환 = {qr_data}"
                )
                return response

        self.scan_running = False
        self.monitoring_active = False
        response.success = False
        response.message = "RCLPY_SHUTDOWN"
        return response

    def camera_timer_callback(self):
        """
        QR 인식 성공 후 이물질 감시를 계속 수행한다.

        scan_qr 서비스가 QR을 찾는 동안에는 서비스 콜백 내부에서 프레임을 처리하므로,
        timer에서는 중복으로 프레임을 처리하지 않는다.
        """
        if self.scan_running:
            return

        if not self.monitoring_active or self.vision is None:
            return

        if not self.vision.camera.is_opened():
            self.get_logger().error("카메라가 열려 있지 않습니다.")
            self.monitoring_active = False
            return

        success, frame = self.vision.camera.read()
        if not success:
            self.get_logger().error("카메라 프레임 수신 실패")
            return

        self.vision.last_frame_time = time.monotonic()
        self.vision.process_frame(frame)

        # main_vision.py의 run()과 동일하게 OpenCV 키 입력 처리
        key = cv2.waitKey(1) & 0xFF

        if key == 27:  # ESC
            self.get_logger().info("ESC 입력: 비전 처리 중지")
            self.stop_vision()

        elif key == ord("d"):
            self.vision.toggle_debug_masks()

    def qr_confirmed_callback(self, payload):
        """
        BookVision.confirm_qr()에서 QR 인식 성공 시 호출된다.
        여기서는 topic publish가 아니라, scan_qr 서비스 응답으로 반환할 값을 저장한다.
        """
        self.latest_qr_payload = payload
        self.latest_qr_data = payload.get("qr_data", "")

        self.get_logger().info(f"QR 확인 callback 수신: {self.latest_qr_data}")

    def emergency_stop_callback(self, detected):
        """
        BookVision에서 이물질 알람/해제 상태가 넘어오면 컨트롤러로 publish한다.
        중복 publish를 줄이기 위해 상태가 바뀔 때만 publish한다.
        """
        detected = bool(detected)

        if detected == self.last_emergency_stop:
            return

        self.last_emergency_stop = detected

        message = Bool()
        message.data = detected
        self.emergency_stop_publisher.publish(message)

        if detected:
            self.get_logger().warning("이물질 알람 발생: /vision/emergency_stop = True publish")
        else:
            self.get_logger().info("이물질 알람 해제: /vision/emergency_stop = False publish")

    def status_callback(self, code, message):
        """BookVision 상태 메시지를 JSON 문자열로 publish한다."""
        status_message = String()
        status_message.data = json.dumps(
            {
                "code": code,
                "message": message,
            },
            ensure_ascii=False,
        )
        self.status_publisher.publish(status_message)

    def stop_vision(self):
        """카메라와 OpenCV 창을 닫고, 다음 /vision/scan_qr 요청을 기다릴 수 있게 한다."""
        self.scan_running = False
        self.monitoring_active = False
        self.last_emergency_stop = False
        self.latest_qr_data = None
        self.latest_qr_payload = None

        if self.vision is not None:
            self.vision.close()
            self.vision = None

        cv2.destroyAllWindows()
        self.get_logger().info("비전 처리 중지: 다시 /vision/scan_qr 요청 대기")

    def destroy_node(self):
        self.stop_vision()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BookVisionRosBridge()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

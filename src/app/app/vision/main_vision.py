import time

import cv2
try:
    from app.vision.camera_manager import CameraManager
    from app.vision.intrusion_detector import IntrusionDetector
    from app.vision.qr_detector import QRDetector
    from app.vision.robot_marker_detector import RobotMarkerDetector
    from app.vision.vision_state import VisionState
    from app.vision.visualizer import Visualizer
except Exception as e:
    from camera_manager import CameraManager
    from intrusion_detector import IntrusionDetector
    from qr_detector import QRDetector
    from robot_marker_detector import RobotMarkerDetector
    from vision_state import VisionState
    from visualizer import Visualizer


class BookVision:
    """
    역할:
    - 전체 비전 시스템의 메인 제어 클래스다.
    - 카메라, QR 인식기, 로봇팔 마커 감지기, 이물질 감지기, 화면 표시기를 조합한다.
    - QR 인식 전 상태와 QR 확정 후 로봇 작업/이물질 감지 상태를 전환한다.
    """

    def __init__(
        self,
        camera_index=2,
        on_qr_confirmed=None,
        on_status=None,
        on_stop_required=None,
        on_frame=None,
    ):
        self.on_qr_confirmed = on_qr_confirmed
        self.on_status = on_status
        self.on_stop_required = on_stop_required

        self.camera = CameraManager(camera_index=camera_index)
        self.state = VisionState()

        # ==========================================================
        # 공통 ROI 설정
        # ==========================================================
        # QR 인식 전 QR 탐색 영역과 QR 인식 후 이물질 감지 영역을
        # 동일한 크기/위치로 사용한다.
        # 기존 QR ROI: (600, 150, 450, 400)
        # 기존 이물질 감지 ROI: (520, 120, 560, 560)
        # 요청에 따라 인식 성공 후 ROI 크기인 아래 값으로 통일한다.
        self.common_roi = (520, 120, 560, 560)
        self.intrusion_roi = self.common_roi

        self.qr_detector = QRDetector(qr_roi=self.common_roi)
        self.robot_marker_detector = RobotMarkerDetector()
        self.intrusion_detector = IntrusionDetector()
        self.visualizer = Visualizer(on_frame=on_frame)

        # 책 감지는 하지 않지만, 외부 콜백 호환을 위해 None으로 유지한다.
        self.book_bbox = None

        self.qr_points = None
        self.locked_qr_data = None

        self.scan_start_time = time.monotonic()
        self.qr_timeout = 5.0

        self.last_frame_time = time.monotonic()
        self.camera_timeout = 2.0

        self.running = False
        self.show_debug_masks = False

        self.last_status_code = None
        self.last_status_message = None

        self.publish_status("READY", "QR 인식 대기 중")

    def run(self):
        """
        카메라 프레임을 계속 읽고 process_frame()으로 전달하는 메인 루프다.
        ESC 종료, r 재시작, d 디버그 마스크 토글을 처리한다.
        """
        if not self.camera.is_opened():
            self.publish_status("CAMERA_ERROR", "카메라를 열 수 없습니다.")
            return

        self.running = True

        while self.running:
            success, frame = self.camera.read()

            if not success:
                elapsed = time.monotonic() - self.last_frame_time
                if elapsed >= self.camera_timeout:
                    self.publish_status("CAMERA_ERROR", "카메라 영상이 수신되지 않습니다.")
                    break
                continue

            self.last_frame_time = time.monotonic()
            self.process_frame(frame)

            # OpenCV 창을 직접 띄우는 경우 키 입력 처리
            if self.visualizer.on_frame is None:
                key = cv2.waitKey(1) & 0xFF

                # ESC
                if key == 27:
                    break

                # r: QR 인식 재시작
                if key == ord("r"):
                    self.resume_scan()

                # d: 디버그 마스크 표시 토글
                if key == ord("d"):
                    self.toggle_debug_masks()

        self.close()

    def process_frame(self, frame):
        """
        한 프레임에 대한 전체 처리 흐름을 담당한다.

        상태 흐름:
        1. 위험 상태: 모든 작업 중지 표시
        2. QR 확정 전: QR ROI 안에서 QR 탐색
        3. QR 확정 후: 로봇 작업 중 이물질 감지
        """
        if self.state.danger_detected:
            self.visualizer.draw_roi(frame, self.intrusion_roi)
            self.visualizer.draw_text(frame, "DANGER - STOP REQUIRED", (0, 0, 255))
            self.visualizer.show_frame(frame)
            return

        if not self.state.scan_enabled:
            self.process_working_frame(frame)
            return

        self.process_qr_scanning_frame(frame)
         
    def process_qr_scanning_frame(self, frame):
        """
        QR 확정 전 상태의 프레임 처리.
        책 감지는 하지 않고 QR ROI 안에서 QR만 탐색한다.
        """
        self.book_bbox = None

        # QR 인식 전에도 QR 전용 ROI가 아니라 공통 ROI를 표시한다.
        # QR 탐색 영역과 이물질 감지 영역이 같은 위치/크기로 보이게 하기 위함이다.
        self.visualizer.draw_qr_roi(frame, self.common_roi)
        qr_result = self.qr_detector.detect(frame)

        if qr_result["points"] is not None:
            self.qr_points = qr_result["points"]
            self.visualizer.draw_qr_box(frame, self.qr_points)

        status = qr_result["status"]

        if status == "SUCCESS":
            qr_data = qr_result["data"]
            self.visualizer.draw_text(frame, f"QR OK: {qr_data}", (0, 255, 0))
            self.draw_qr_data_overlay(frame, qr_data)
            self.confirm_qr(qr_data)

        elif status == "DECODE_ERROR":
            self.publish_status("QR_DECODE_ERROR", qr_result["message"])
            self.visualizer.draw_text(frame, "QR DECODE FAILED", (0, 0, 255))

        elif status == "NOT_FOUND":
            self.qr_points = None
            self.check_qr_timeout(frame)

        elif status == "ROI_ERROR":
            self.publish_status("ROI_ERROR", qr_result["message"])
            self.visualizer.draw_text(frame, "QR ROI ERROR", (0, 0, 255))

        self.visualizer.show_frame(frame)

    def process_working_frame(self, frame):
        """
        QR 확정 후 로봇 작업 상태의 프레임 처리.
        QR 인식은 중단하고 이물질 감지만 수행한다.
        """
        self.visualizer.draw_roi(frame, self.intrusion_roi)

        if self.state.intrusion_monitor_enabled:
            monitor_bbox = self.intrusion_roi
            self.visualizer.draw_intrusion_area(frame, monitor_bbox)

            # 1. 로봇팔 파란색 스티커 감지
            marker_centers, marker_bboxes = self.robot_marker_detector.detect_stickers(frame)

            # 2. 현재 로봇팔 mask 생성
            robot_arm_mask = self.robot_marker_detector.build_arm_mask(frame, marker_centers)

            # 3. 현재 + 최근 로봇팔 mask를 합쳐 제외 영역 생성
            robot_ignore_mask = self.robot_marker_detector.build_ignore_mask(robot_arm_mask)

            # 4. 로봇팔 빠른 이동 여부 판단
            robot_fast_moving = self.robot_marker_detector.update_motion_state(marker_centers)

            # 5. 로봇팔 표시
            self.visualizer.draw_robot_markers(frame, marker_centers, marker_bboxes)

            # 6. ROI 전체에서 피부색 + 움직임 기반 장애물 감지
            intrusion_result = self.intrusion_detector.detect(
                frame,
                monitor_bbox,
                use_motion=not robot_fast_moving,
                use_skin=True,
                ignore_mask=robot_ignore_mask,
            )

            # 7. 연속 프레임 조건으로 알람 처리
            self.handle_intrusion_alarm(frame, intrusion_result)

            # 8. 현재 로봇팔 mask를 history에 저장
            self.robot_marker_detector.update_prev_arm_mask(robot_arm_mask)

            if robot_fast_moving:
                self.visualizer.draw_text(
                    frame,
                    "ROBOT FAST MOVING - MOTION IGNORED",
                    (0, 165, 255),
                    position=(20, 180),
                )

        if self.qr_points is not None:
            self.visualizer.draw_qr_box(frame, self.qr_points)

        if self.locked_qr_data:
            self.draw_qr_data_overlay(frame, self.locked_qr_data)

        status_text = "ROBOT WORKING" if self.state.robot_working else "SCAN PAUSED"
        self.visualizer.draw_text(frame, status_text, (0, 255, 255), position=(20, 100))
        self.visualizer.show_frame(frame)

    def draw_qr_data_overlay(self, frame, qr_data):
        """
        QR 코드 안에 들어있는 데이터를 화면 하단에 표시한다.

        주의:
        - OpenCV의 cv2.putText는 기본적으로 한글 출력이 약하므로,
          QR 데이터가 한글이면 화면에서 깨져 보일 수 있다.
        - 숫자, 영문, URL, 코드값은 정상적으로 표시된다.
        """
        if qr_data is None:
            return

        text = str(qr_data)
        if not text:
            return

        frame_h, frame_w = frame.shape[:2]

        max_chars = 48
        data_lines = [
            text[i:i + max_chars]
            for i in range(0, len(text), max_chars)
        ]

        # 화면을 너무 많이 가리지 않도록 최대 3줄까지만 표시
        if len(data_lines) > 3:
            data_lines = data_lines[:3]
            data_lines[-1] = data_lines[-1][:max(0, max_chars - 3)] + "..."

        lines = ["QR DATA:"] + data_lines

        x = 20
        line_gap = 28
        box_padding = 10
        box_height = line_gap * len(lines) + box_padding * 2
        y_top = max(10, frame_h - box_height - 15)
        y_text = y_top + box_padding + 20

        # 가독성을 위해 검은 배경 박스를 깐다.
        box_width = min(frame_w - 20, 720)
        cv2.rectangle(
            frame,
            (10, y_top),
            (box_width, y_top + box_height),
            (0, 0, 0),
            -1,
        )

        for index, line in enumerate(lines):
            color = (0, 255, 0) if index == 0 else (255, 255, 255)
            cv2.putText(
                frame,
                line,
                (x, y_text + index * line_gap),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

    def handle_intrusion_alarm(self, frame, intrusion_result):
        """이물질 감지 결과를 기반으로 알람 표시와 상태 발행을 처리한다."""
        intrusion_bboxes = intrusion_result["bboxes"]
        intrusion_ratio = intrusion_result["bbox_ratio"]

        alarm_result = self.intrusion_detector.update_alarm(intrusion_result["detected"])

        if intrusion_result["detected"]:
            if alarm_result["alarm"]:
                self.visualizer.draw_intrusion_boxes(frame, intrusion_bboxes)
                self.visualizer.show_alarm_message(frame, "ALARM: ROI AREA INTRUSION")
                self.raise_intrusion_alarm(intrusion_ratio)
            else:
                self.visualizer.draw_text(
                    frame,
                    (
                        "INTRUSION CHECK "
                        f"{alarm_result['count']}/{self.intrusion_detector.confirm_frames}"
                    ),
                    (0, 165, 255),
                    position=(20, 140),
                )
            return

        if alarm_result["cleared"]:
            self.clear_intrusion_alarm()

    def confirm_qr(self, qr_data):
        """
        QR 데이터가 정상적으로 인식되었을 때 호출된다.
        QR 스캔을 멈추고 로봇 작업 및 이물질 감지 상태로 전환한다.
        """
        self.state.set_qr_confirmed()
        self.locked_qr_data = qr_data
        self.intrusion_detector.reset()
        self.robot_marker_detector.reset()

        qr_bbox = None
        if self.qr_points is not None:
            qr_x, qr_y, qr_w, qr_h = cv2.boundingRect(self.qr_points)
            qr_bbox = (qr_x, qr_y, qr_w, qr_h)

        payload = {
            "qr_data": qr_data,
            "book_bbox": self.book_bbox,
            "qr_bbox": qr_bbox,
        }

        if self.on_qr_confirmed is not None:
            self.on_qr_confirmed(payload)

        self.publish_status("QR_CONFIRMED", f"QR 확정: {qr_data}")
        print(f"QR confirmed payload: {payload}")

    def ready_callback(self, ready):
        """
        외부에서 로봇 복귀/준비 완료 신호를 받았을 때 호출된다.
        다음 QR 인식을 시작할 수 있도록 상태를 초기화한다.
        """
        if not ready or self.state.danger_detected:
            return

        self.reset_runtime_state()
        self.publish_status("READY", "로봇 복귀 완료, 다음 QR 인식 시작")

    def danger_callback(self, detected):
        """
        외부 위험 감지 신호를 받았을 때 호출된다.
        위험 감지 시 QR 인식과 로봇 작업을 멈추고 정지 요청 콜백을 호출할 수 있다.
        """
        self.state.set_danger(detected)

        if self.on_stop_required is not None:
            self.on_stop_required(detected)

        if detected:
            self.publish_status("DANGER", "위험 객체 감지, 정지 요청")
        else:
            self.publish_status("DANGER_CLEARED", "위험 해제, 재시작 승인 필요")

    def resume_scan(self):
        """
        수동으로 QR 인식을 다시 시작한다.
        위험 상태가 아니면 내부 상태를 초기화하고 QR 스캔 상태로 돌아간다.
        """
        if self.state.danger_detected:
            self.publish_status("DANGER", "위험 상태이므로 재시작할 수 없습니다.")
            return

        self.reset_runtime_state()
        self.publish_status("READY", "QR 인식을 다시 시작합니다.")

    def reset_runtime_state(self):
        """QR, 로봇팔 마스크, 이물질 감지, 타이머 등 런타임 상태를 초기화한다."""
        self.state.reset_scan()
        self.book_bbox = None
        self.qr_points = None
        self.locked_qr_data = None
        self.intrusion_detector.reset()
        self.robot_marker_detector.reset()
        self.scan_start_time = time.monotonic()

    def check_qr_timeout(self, frame):
        """QR을 일정 시간 이상 찾지 못했는지 확인하고 상태 메시지를 표시한다."""
        elapsed = time.monotonic() - self.scan_start_time

        if elapsed >= self.qr_timeout:
            self.publish_status("QR_NOT_FOUND", "QR 코드를 찾지 못했습니다.")
            self.visualizer.draw_text(frame, "QR NOT FOUND", (0, 0, 255))
        else:
            self.publish_status("QR_SCANNING", "QR 탐색 중")
            self.visualizer.draw_text(frame, "SCANNING QR...", (255, 255, 0))

    def raise_intrusion_alarm(self, intrusion_ratio):
        """
        이물질 침범 알람 상태 메시지를 발행한다.
        필요하면 on_stop_required(True)를 연결해 로봇 정지까지 수행할 수 있다.
        """
        self.publish_status("ROI_INTRUSION_ALARM", f"ROI 영역 침범 감지: {intrusion_ratio:.2%}")

        # ROS wrapper가 연결되어 있으면 컨트롤러 쪽으로 비상정지 요청을 전달한다.
        if self.on_stop_required is not None:
            self.on_stop_required(True)

    def clear_intrusion_alarm(self):
        """
        이물질 침범 알람 해제 상태 메시지를 발행한다.
        필요하면 on_stop_required(False)를 연결해 정지 해제까지 수행할 수 있다.
        """
        self.publish_status("ROI_INTRUSION_CLEARED", "ROI 영역 침범 알람 해제")

        # 알람이 해제되었을 때도 컨트롤러 쪽으로 해제 상태를 전달한다.
        if self.on_stop_required is not None:
            self.on_stop_required(False)

    def publish_status(self, code, message):
        """
        상태 메시지를 외부 콜백으로 전달하거나 콘솔에 출력한다.
        같은 메시지가 반복 출력되지 않도록 중복 발행을 막는다.
        """
        if self.last_status_code == code and self.last_status_message == message:
            return

        self.last_status_code = code
        self.last_status_message = message

        if self.on_status is not None:
            self.on_status(code, message)
        else:
            print(f"{code}|{message}")

    def toggle_debug_masks(self):
        """QR/로봇팔/이물질 감지 디버그 마스크 창 표시 여부를 토글한다."""
        self.show_debug_masks = not self.show_debug_masks
        self.robot_marker_detector.show_debug_masks = self.show_debug_masks
        self.intrusion_detector.show_debug_masks = self.show_debug_masks
        print(f"show_debug_masks = {self.show_debug_masks}")

    def stop(self):
        """run() 루프를 종료한다."""
        self.running = False

    def close(self):
        """카메라 자원을 해제하고 OpenCV 창을 닫는다."""
        self.running = False
        self.camera.close()
        cv2.destroyAllWindows()


def main():
    """이 파일을 직접 실행했을 때 BookVision 객체를 만들고 실행한다."""
    vision = BookVision(camera_index=2)

    try:
        vision.run()
    except KeyboardInterrupt:
        pass
    finally:
        vision.close()


if __name__ == "__main__":
    main()

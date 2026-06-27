import sys
import threading

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QMessageBox
)

from std_srvs.srv import Empty
from interfaces.srv import UiErrorResponse, UiErrorNotify


class UISignals(QObject):
    error_notify = pyqtSignal(int)


class TestUINode(Node):
    def __init__(self, signals: UISignals):
        super().__init__("test_ui_node")
        self.signals = signals

        self.cleanup_cli = self.create_client(
            Empty,
            "/controller/cleanup_request"
        )

        self.error_response_cli = self.create_client(
            UiErrorResponse,
            "/controller/error_response"
        )

        self.error_notify_srv = self.create_service(
            UiErrorNotify,
            "/ui/error_notify",
            self.handle_error_notify
        )

    def request_cleanup(self):
        if not self.cleanup_cli.service_is_ready():
            self.get_logger().error("cleanup_request service not ready")
            return False

        future = self.cleanup_cli.call_async(Empty.Request())
        future.add_done_callback(self.on_cleanup_response)
        return True

    def on_cleanup_response(self, future):
        try:
            future.result()
            self.get_logger().info("cleanup_request success")
        except Exception as e:
            self.get_logger().error(f"cleanup_request failed: {e}")

    def request_error_response(self, code: int):
        if not self.error_response_cli.service_is_ready():
            self.get_logger().error("error_response service not ready")
            return False

        req = UiErrorResponse.Request()
        req.code = int(code)

        future = self.error_response_cli.call_async(req)
        future.add_done_callback(self.on_error_response)
        return True

    def on_error_response(self, future):
        try:
            res = future.result()
            self.get_logger().info(
                f"error_response result: success={res.success}, message={res.message}"
            )
        except Exception as e:
            self.get_logger().error(f"error_response failed: {e}")

    def handle_error_notify(self, request, response):
        code = int(request.code)
        self.get_logger().warn(f"error_notify received: code={code}")

        self.signals.error_notify.emit(code)

        response.success = True
        response.message = "UI received error_notify"
        return response


class TempMainWindow(QMainWindow):
    ERROR_MESSAGE = {
        0: "엔트리포인트 이물질 감지",
        1: "로봇 안전정지상태 돌입",
        2: "태스크 진행 중 걸림/충돌/놓침",
        3: "비상정지 버튼",
        4: "데이터 검색 불가",
    }

    RESPONSE_TEXT = {
        0: "재시작",
        1: "수동제어",
        2: "태스크 초기화",
    }

    def __init__(self, ui_node: TestUINode, signals: UISignals):
        super().__init__()
        self.ui_node = ui_node
        self.signals = signals

        self.setWindowTitle("도서 자동정리 로봇 제어 UI")
        self.resize(560, 380)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f3f5f7;
            }

            QLabel#TitleLabel {
                font-size: 24px;
                font-weight: 700;
                color: #1f2937;
            }

            QLabel#SubTitleLabel {
                font-size: 13px;
                color: #6b7280;
            }

            QLabel#StatusLabel {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
                color: #111827;
            }

            QLabel#SectionLabel {
                font-size: 15px;
                font-weight: 600;
                color: #374151;
                margin-top: 8px;
            }

            QPushButton {
                min-height: 42px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                background-color: #e5e7eb;
                color: #111827;
            }

            QPushButton:hover {
                background-color: #d1d5db;
            }

            QPushButton#PrimaryButton {
                background-color: #2563eb;
                color: white;
            }

            QPushButton#PrimaryButton:hover {
                background-color: #1d4ed8;
            }

            QPushButton#WarningButton {
                background-color: #f59e0b;
                color: white;
            }

            QPushButton#WarningButton:hover {
                background-color: #d97706;
            }

            QPushButton#DangerButton {
                background-color: #dc2626;
                color: white;
            }

            QPushButton#DangerButton:hover {
                background-color: #b91c1c;
            }
        """)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("도서 자동정리 로봇 제어 패널")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        subtitle = QLabel("Controller 상태 확인 · 정리 요청 · 예외 대응")
        subtitle.setObjectName("SubTitleLabel")
        layout.addWidget(subtitle)

        self.status_label = QLabel("상태: 대기 중")
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label)

        control_label = QLabel("기본 제어")
        control_label.setObjectName("SectionLabel")
        layout.addWidget(control_label)

        cleanup_btn = QPushButton("서가 / 작업공간 정리 요청")
        cleanup_btn.setObjectName("PrimaryButton")
        cleanup_btn.clicked.connect(self.on_cleanup_clicked)
        layout.addWidget(cleanup_btn)

        error_label = QLabel("예외 상황 대응")
        error_label.setObjectName("SectionLabel")
        layout.addWidget(error_label)

        error_layout = QHBoxLayout()
        error_layout.setSpacing(10)

        restart_btn = QPushButton("재시작")
        restart_btn.setObjectName("PrimaryButton")
        restart_btn.clicked.connect(lambda: self.on_error_response_clicked(0))
        error_layout.addWidget(restart_btn)

        manual_btn = QPushButton("수동 제어")
        manual_btn.setObjectName("WarningButton")
        manual_btn.clicked.connect(lambda: self.on_error_response_clicked(1))
        error_layout.addWidget(manual_btn)

        reset_btn = QPushButton("태스크 초기화")
        reset_btn.setObjectName("DangerButton")
        reset_btn.clicked.connect(lambda: self.on_error_response_clicked(2))
        error_layout.addWidget(reset_btn)

        layout.addLayout(error_layout)

        hint = QLabel(
            "※ 예외 알림 수신 시 팝업이 표시되며, 상황에 따라 위 대응 버튼을 선택합니다."
        )
        hint.setObjectName("SubTitleLabel")
        layout.addWidget(hint)

        self.setCentralWidget(root)

        self.signals.error_notify.connect(self.show_error_dialog)

    def on_cleanup_clicked(self):
        ok = self.ui_node.request_cleanup()

        if ok:
            self.status_label.setText("상태: 정리 요청 전송됨")
        else:
            QMessageBox.critical(
                self,
                "서비스 오류",
                "/controller/cleanup_request service가 준비되지 않았습니다."
            )

    def on_error_response_clicked(self, code: int):
        ok = self.ui_node.request_error_response(code)

        text = self.RESPONSE_TEXT.get(code, "알 수 없는 대응")

        if ok:
            self.status_label.setText(f"상태: 예외 대응 전송됨 - {text}")
        else:
            QMessageBox.critical(
                self,
                "서비스 오류",
                "/controller/error_response service가 준비되지 않았습니다."
            )

    def show_error_dialog(self, code: int):
        message = self.ERROR_MESSAGE.get(
            code,
            f"알 수 없는 오류 코드: {code}"
        )

        self.status_label.setText(f"상태: 예외 수신 - code={code}")

        QMessageBox.warning(
            self,
            "로봇 예외 정지 알림",
            f"[오류 코드] {code}\n\n[내용]\n{message}"
        )


def main(args=None):
    rclpy.init(args=args)

    app = QApplication(sys.argv)

    signals = UISignals()
    ui_node = TestUINode(signals)

    executor = MultiThreadedExecutor()
    executor.add_node(ui_node)

    ros_thread = threading.Thread(
        target=executor.spin,
        daemon=True
    )
    ros_thread.start()

    window = TempMainWindow(ui_node, signals)
    window.show()

    try:
        app.exec()
    finally:
        executor.shutdown()
        ui_node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
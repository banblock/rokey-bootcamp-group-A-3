import sys
import os
import qrcode
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QPushButton, QLabel,
    QDialog, QLineEdit, QFormLayout, QMessageBox, QProgressBar,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap


class SystemConfig:
    # ui_node.py에서 실제 ROS 서비스명으로 매핑한다.
    # Controller 기준:
    #   UI -> Controller : /controller/cleanup_request, /controller/error_response
    #   Controller -> UI : /ui/error_notify, /ui/task_complite
    SERVICE_CLEANUP_REQUEST = "cleanup_request"
    SERVICE_SORT_REQUEST = SERVICE_CLEANUP_REQUEST
    SERVICE_ERROR_RESPONSE = "error_response"

    SERVICE_ACCEPT = 0
    SERVICE_REJECT = 1

    ACTION_RESTART = 0
    ACTION_MANUAL_CONTROL = 1
    ACTION_TASK_RESET = 2

    ACTION_LABEL = {
        ACTION_RESTART: "재시작",
        ACTION_MANUAL_CONTROL: "수동제어",
        ACTION_TASK_RESET: "테스크 초기화",
    }

    EXCEPTION_STOP_MSG = {
        0: {
            "title": "엔트리포인트 이물질 감지",
            "message": "엔트리포인트에 이물질이 감지되었습니다.\n이물질을 제거한 후 재시작하세요.",
            "level": "warning",
        },
        1: {
            "title": "로봇 안전정지상태 돌입",
            "message": "로봇이 안전정지상태에 들어갔습니다.\n사용자 수동제어 후 테스크 초기화를 진행하세요.",
            "level": "error",
        },
        2: {
            "title": "테스크 진행 중 이상 발생",
            "message": "테스크 진행 중 걸림, 충돌 또는 놓침이 감지되었습니다.\n상태 확인 후 재시작, 수동제어 또는 초기화를 선택하세요.",
            "level": "error",
        },
        3: {
            "title": "비상정지 버튼 입력",
            "message": "비상정지 버튼이 눌렸습니다.\n사용자 수동제어 후 테스크 초기화를 진행하세요.",
            "level": "emergency",
        },
        4: {
            "title": "데이터 검색 불가",
            "message": "도서 데이터를 찾을 수 없습니다.\n사용자에게 알린 후 초기화를 진행하세요.",
            "level": "error",
        },
    }
    EXCEPTION_ACTION_POLICY = {
        0: {
            "restart": True,
            "manual": False,
            "reset": False,
            "reset_after_manual": False,
        },
        1: {
            "restart": False,
            "manual": True,
            "reset": False,
            "reset_after_manual": True,
        },
        2: {
            "restart": True,
            "manual": True,
            "reset": False,
            "reset_after_manual": True,
        },
        3: {
            "restart": False,
            "manual": True,
            "reset": False,
            "reset_after_manual": True,
        },
        4: {
            "restart": False,
            "manual": False,
            "reset": True,
            "reset_after_manual": False,
        },
    }
    SIZE_LIMITS = {
        "max_w": 30.0,
        "max_h": 20.0,
        "max_d": 5.0,
        "min_w": 15.0,
        "min_h": 10.0,
        "min_d": 1.0
    }

    CAMERA_WAITING_TEXT = "📷 실시간 카메라 화면\n(카메라 수신 대기 중)"
    CAMERA_BLACK_STYLE = (
        "background-color: black; color: #aaaaaa; "
        "font-size: 14px; border: 2px solid #333;"
    )
    CAMERA_TIMEOUT_MS = 1000


class QRDisplayDialog(QDialog):
    def __init__(self, book_id, title, qr_code, parent=None):
        super().__init__(parent)
        self.setWindowTitle("도서 QR 코드 생성 완료")
        self.setFixedSize(360, 420)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info_lbl = QLabel(
            f"<b>도서 등록 완료</b><br>"
            f"도서 ID: <font color='black'>{book_id}</font><br>"
            f"제목: {title}",
            self
        )
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_lbl.setStyleSheet("font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(info_lbl)

        lbl_title = QLabel("[도서 QR]", self)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(lbl_title)

        self.qr_label = QLabel(self)
        self.qr_label.setFixedSize(220, 220)
        self.qr_label.setStyleSheet(
            "border: 1px solid #ccc; background-color: white;"
        )
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label)

        self.generate_and_display_qr(qr_code)

        confirm_btn = QPushButton("확인 및 인쇄 완료", self)
        confirm_btn.setStyleSheet(
            "font-weight: bold; padding: 8px; margin-top: 15px;"
        )
        confirm_btn.clicked.connect(self.accept)
        layout.addWidget(confirm_btn)

    def generate_and_display_qr(self, qr_code):
        try:
            qr_save_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "generated_qr"
            )
            os.makedirs(qr_save_dir, exist_ok=True)

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_Q,
                box_size=10,
                border=2
            )
            qr.add_data(qr_code)
            qr.make(fit=True)

            pil_img = qr.make_image(
                fill_color="black",
                back_color="white"
            ).convert("RGB")

            save_path = os.path.join(
                qr_save_dir,
                f"QR_{qr_code}.png"
            )
            pil_img.save(save_path)

            width, height = pil_img.size
            bytes_per_line = 3 * width

            q_img = QImage(
                pil_img.tobytes(),
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888
            ).copy()
            pixmap = QPixmap.fromImage(q_img)

            self.qr_label.setPixmap(
                pixmap.scaled(
                    self.qr_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio
                )
            )

        except Exception:
            QMessageBox.critical(
                self,
                "QR 생성 오류",
                "QR 코드 생성 중 오류가 발생했습니다."
            )


class BookRegistrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("신규 도서 등록")
        self.setFixedSize(360, 240)

        layout = QFormLayout(self)

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("책 제목 입력")

        self.shelf_input = QLineEdit(self)
        self.shelf_input.setValidator(QIntValidator(1, 4, self))
        self.shelf_input.setPlaceholderText("섹션 번호 (1~4)")

        self.size_w_input = QLineEdit(self)
        self.size_h_input = QLineEdit(self)
        self.size_d_input = QLineEdit(self)

        double_validator = QDoubleValidator(0.0, 99.9, 2, self)
        self.size_w_input.setValidator(double_validator)
        self.size_h_input.setValidator(double_validator)
        self.size_d_input.setValidator(double_validator)

        size_layout = QHBoxLayout()
        size_layout.addWidget(self.size_w_input)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.size_h_input)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.size_d_input)

        layout.addRow("도서 제목:", self.name_input)
        layout.addRow("배정 섹션:", self.shelf_input)
        layout.addRow("사이즈 (cm):", size_layout)

        self.reg_btn = QPushButton("등록 및 QR 생성", self)
        self.reg_btn.clicked.connect(self.handle_registration)
        layout.addWidget(self.reg_btn)

    def handle_registration(self):
        title = self.name_input.text().strip()
        section = self.shelf_input.text().strip()
        w_str = self.size_w_input.text().strip()
        h_str = self.size_h_input.text().strip()
        d_str = self.size_d_input.text().strip()

        if not title or not section or not w_str or not h_str or not d_str:
            QMessageBox.warning(self, "입력 오류", "모든 칸을 입력해 주세요.")
            return

        try:
            w, h, d = float(w_str), float(h_str), float(d_str)
            section_num = int(section)
            if not 1 <= section_num <= 4:
                QMessageBox.warning(
                    self,
                    "입력 오류",
                    "섹션 번호는 1~4 사이여야 합니다."
                )
                return
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "올바른 숫자를 입력해 주세요.")
            return

        limits = SystemConfig.SIZE_LIMITS

        if not (
            limits["min_w"] <= w <= limits["max_w"]
            and limits["min_h"] <= h <= limits["max_h"]
            and limits["min_d"] <= d <= limits["max_d"]
        ):
            QMessageBox.critical(
                self,
                "규격 초과/미달",
                "허용 범위를 벗어난 도서입니다."
            )
            return

        self.registered_data = {
            "title": title,
            "section": section_num,
            "dimensions": [w, h, d]
        }

        self.accept()




class ExceptionStopDialog(QDialog):
    def __init__(self, code, main_app, parent=None):
        super().__init__(parent)
        self.code = int(code)
        self.main_app = main_app
        self.manual_control_done = False
        self.policy = SystemConfig.EXCEPTION_ACTION_POLICY.get(
            self.code,
            {
                "restart": False,
                "manual": False,
                "reset": False,
                "reset_after_manual": False,
            }
        )

        info = SystemConfig.EXCEPTION_STOP_MSG.get(
            self.code,
            {
                "title": "알 수 없는 예외 정지",
                "message": "정의되지 않은 예외 정지 코드가 수신되었습니다.",
                "level": "error",
            }
        )

        self.setWindowTitle("예외 정지 알림")
        self.setFixedSize(520, 330)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.CustomizeWindowHint
        )
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)

        if info.get("level") == "emergency":
            title_text = "🚨 EXCEPTION STOP"
            title_style = (
                "font-size: 20px; color: white; font-weight: bold; "
                "background-color: #660000; padding: 8px;"
            )
        elif info.get("level") == "warning":
            title_text = "⚠️ EXCEPTION STOP"
            title_style = (
                "font-size: 20px; color: #ff9800; font-weight: bold; "
                "padding: 8px;"
            )
        else:
            title_text = "❌ EXCEPTION STOP"
            title_style = (
                "font-size: 20px; color: red; font-weight: bold; "
                "padding: 8px;"
            )

        title = QLabel(title_text, alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(title_style)
        layout.addWidget(title)

        content = QLabel(
            f"코드: {self.code}\n"
            f"원인: {info.get('title')}\n\n"
            f"{info.get('message')}",
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        content.setWordWrap(True)
        content.setStyleSheet("font-size: 13px; padding: 8px;")
        layout.addWidget(content)

        self.status_label = QLabel(
            "초기화는 반드시 수동제어 요청 후 실행할 수 있습니다.",
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.status_label.setStyleSheet(
            "font-size: 12px; color: #555; padding: 4px;"
        )
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()

        self.restart_btn = QPushButton("재시작", self)
        self.restart_btn.setStyleSheet(
            "padding: 8px; font-weight: bold; background-color: #e8f5e9;"
        )
        self.restart_btn.clicked.connect(
            lambda: self.request_action(SystemConfig.ACTION_RESTART)
        )
        btn_layout.addWidget(self.restart_btn)

        self.manual_btn = QPushButton("수동제어", self)
        self.manual_btn.setStyleSheet(
            "padding: 8px; font-weight: bold; background-color: #fff3e0;"
        )
        self.manual_btn.clicked.connect(
            lambda: self.request_action(SystemConfig.ACTION_MANUAL_CONTROL)
        )
        btn_layout.addWidget(self.manual_btn)

        self.reset_btn = QPushButton("테스크 초기화", self)
        self.reset_btn.setStyleSheet(
            "padding: 8px; font-weight: bold; background-color: #e3f2fd;"
        )
        self.reset_btn.setEnabled(False)
        self.reset_btn.clicked.connect(
            lambda: self.request_action(SystemConfig.ACTION_TASK_RESET)
        )
        btn_layout.addWidget(self.reset_btn)

        layout.addLayout(btn_layout)

        self.apply_action_policy()

    def apply_action_policy(self):
        self.restart_btn.setVisible(self.policy.get("restart", False))
        self.manual_btn.setVisible(self.policy.get("manual", False))

        reset_visible = (
            self.policy.get("reset", False)
            or self.policy.get("reset_after_manual", False)
        )
        self.reset_btn.setVisible(reset_visible)

        self.restart_btn.setEnabled(self.policy.get("restart", False))
        self.manual_btn.setEnabled(self.policy.get("manual", False))

        if self.policy.get("reset", False):
            self.reset_btn.setEnabled(True)
        else:
            self.reset_btn.setEnabled(False)

    def set_buttons_enabled(self, enabled):
        self.restart_btn.setEnabled(
            enabled and self.policy.get("restart", False)
        )
        self.manual_btn.setEnabled(
            enabled and self.policy.get("manual", False)
        )

        if self.policy.get("reset", False):
            self.reset_btn.setEnabled(enabled)
        elif self.policy.get("reset_after_manual", False):
            self.reset_btn.setEnabled(enabled and self.manual_control_done)
        else:
            self.reset_btn.setEnabled(False)

    def request_action(self, action_code):
        if action_code == SystemConfig.ACTION_TASK_RESET:
            if (
                self.policy.get("reset_after_manual", False)
                and not self.manual_control_done
            ):
                QMessageBox.warning(
                    self,
                    "초기화 불가",
                    "테스크 초기화는 수동제어 완료 후 실행할 수 있습니다."
                )
                return

            if not (
                self.policy.get("reset", False)
                or self.policy.get("reset_after_manual", False)
            ):
                return

        action_name = SystemConfig.ACTION_LABEL.get(action_code, str(action_code))

        sent = self.main_app.request_error_response(action_code)

        if not sent:
            QMessageBox.critical(
                self,
                "서비스 오류",
                f"{action_name} 요청 서비스를 호출하지 못했습니다."
            )
            return

        if action_code == SystemConfig.ACTION_MANUAL_CONTROL:
            self.manual_control_done = True
            self.set_buttons_enabled(True)
            self.status_label.setText(
                "수동제어 요청을 전송했습니다. 이제 테스크 초기화를 실행할 수 있습니다."
            )
            return

        if action_code == SystemConfig.ACTION_TASK_RESET:
            self.main_app.clear_book_display()
            self.main_app.stacked_widget.setCurrentIndex(1)

        self.accept()


class MainApp(QMainWindow):
    service_callback = None

    @classmethod
    def register_service_callback(cls, func):
        cls.service_callback = func

    def __init__(self, db_manager=None):
        super().__init__()
        self.db_manager = db_manager

        self.setWindowTitle("Book Binder Control System")
        self.setGeometry(100, 100, 900, 600)

        self.exception_dialog = None
        self.ros_node = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        top_bar = QHBoxLayout()

        self.emergency_btn = QPushButton("🚨 비상 정지", self)
        self.emergency_btn.setStyleSheet(
            "background-color: red; color: white; "
            "font-weight: bold; padding: 8px;"
        )
        self.emergency_btn.clicked.connect(self.trigger_emergency_stop)
        top_bar.addWidget(self.emergency_btn)

        top_bar.addStretch()

        self.exit_btn = QPushButton("❌ 종료", self)
        self.exit_btn.setStyleSheet("padding: 8px;")
        self.exit_btn.clicked.connect(self.handle_exit_request)
        top_bar.addWidget(self.exit_btn)

        main_layout.addLayout(top_bar)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self.init_slides()

        self.camera_clear_timer = QTimer(self)
        self.camera_clear_timer.setInterval(SystemConfig.CAMERA_TIMEOUT_MS)
        self.camera_clear_timer.setSingleShot(True)
        self.camera_clear_timer.timeout.connect(self.clear_camera_viewer)

        self.stacked_widget.setCurrentIndex(0)
        self.update_top_bar(0)
        self.stacked_widget.currentChanged.connect(self.update_top_bar)

    def init_slides(self):
        slide_start = QWidget()
        l1 = QVBoxLayout(slide_start)

        title = QLabel(
            "📚 도서 관리 시스템",
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; margin-bottom: 20px;"
        )
        l1.addWidget(title)

        start_btn = QPushButton("분류 시작")
        start_btn.setStyleSheet("font-size: 16px; padding: 15px;")
        start_btn.clicked.connect(self.go_to_work_slide)
        l1.addWidget(start_btn)

        self.stacked_widget.addWidget(slide_start)

        slide_work = QWidget()
        l3_main = QHBoxLayout(slide_work)

        self.cam_view = QLabel(
            SystemConfig.CAMERA_WAITING_TEXT,
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.cam_view.setStyleSheet(SystemConfig.CAMERA_BLACK_STYLE)
        self.cam_view.setMinimumSize(480, 360)
        self.cam_view.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored
        )
        self.cam_view.setScaledContents(False)

        l3_main.addWidget(self.cam_view, stretch=1)

        right_part = QVBoxLayout()

        self.work_status_label = QLabel(
            "📚 분류 작업 화면",
            self
        )
        self.work_status_label.setStyleSheet(
            "color: green; font-weight: bold; font-size: 14px;"
        )
        right_part.addWidget(self.work_status_label)

        self.book_info_display = QLabel(
            "📖 현재 분류 중인 도서 정보 없음",
            self
        )
        self.book_info_display.setStyleSheet(
            "background-color: #f9f9f9; padding: 15px; "
            "border-radius: 5px; font-size: 13px; color: black;"
        )
        right_part.addWidget(self.book_info_display)

        right_part.addStretch()

        self.task_reset_btn = QPushButton("🔄 테스크 초기화", self)
        self.task_reset_btn.setStyleSheet(
            "padding: 12px; font-weight: bold; "
            "background-color: #f5f5f5; color: #777;"
        )
        self.task_reset_btn.setEnabled(False)
        self.task_reset_btn.clicked.connect(self.restart_classification_after_complete)
        right_part.addWidget(self.task_reset_btn)

        reg_popup_btn = QPushButton("➕ 신규 책 등록")
        reg_popup_btn.setStyleSheet(
            "padding: 12px; font-weight: bold; "
            "background-color: #e1f5fe; color: black;"
        )
        reg_popup_btn.clicked.connect(self.open_registration_popup)
        right_part.addWidget(reg_popup_btn)

        l3_main.addLayout(right_part, stretch=1)

        self.stacked_widget.addWidget(slide_work)

        slide_shutdown = QWidget()
        l4 = QVBoxLayout(slide_shutdown)
        l4.setAlignment(Qt.AlignmentFlag.AlignCenter)

        shutdown_title = QLabel("시스템 종료 중...", self)
        shutdown_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shutdown_title.setStyleSheet(
            "font-size: 24px; font-weight: bold; margin-bottom: 20px;"
        )
        l4.addWidget(shutdown_title)

        shutdown_desc = QLabel(
            "시스템을 안전하게 종료하고 있습니다.\n"
            "잠시만 기다려주세요.",
            self
        )
        shutdown_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shutdown_desc.setStyleSheet("font-size: 14px;")
        l4.addWidget(shutdown_desc)

        shutdown_pbar = QProgressBar(self)
        shutdown_pbar.setRange(0, 0)
        l4.addWidget(shutdown_pbar)

        self.stacked_widget.addWidget(slide_shutdown)


    def set_ros_node(self, node):
        """
        ui_1.py는 ROS를 직접 모른다.
        ui_node.py가 제공하는 callback/signal만 연결한다.
        """
        self.ros_node = node

        if node is None:
            return

        if hasattr(node, "call_service"):
            MainApp.register_service_callback(node.call_service)
        else:
            raise AttributeError(
                "UINode에는 call_service(service_name, request_data, response_callback=None) 메서드가 필요합니다."
            )

        if hasattr(node, "camera_frame_signal"):
            node.camera_frame_signal.connect(self.update_camera_viewer)

        if hasattr(node, "book_info_signal"):
            node.book_info_signal.connect(self.update_book_display)

        if hasattr(node, "clear_book_signal"):
            # Controller -> UI /ui/task_complite 수신 시
            # 현재 작업 정보를 지우고 작업 화면의 테스크 초기화 버튼을 활성화한다.
            node.clear_book_signal.connect(self.handle_task_complete)

        if hasattr(node, "exception_stop_signal"):
            node.exception_stop_signal.connect(self.trigger_exception_stop)


    def request_service(self, service_name, request_data=None, response_callback=None):
        """
        UI는 ROS service를 직접 호출하지 않는다.
        ui_node.py에 service_name/request_data만 넘긴다.

        이 프로젝트 기준으로 service 응답 내용은 UI 동작에 필수로 사용하지 않는다.
        return 값은 '요청을 보냈는지' 여부만 의미한다.
        """
        if MainApp.service_callback is None:
            return False

        if request_data is None:
            request_data = {}

        try:
            result = MainApp.service_callback(
                service_name,
                request_data,
                response_callback
            )

            if result is None:
                return True

            return bool(result)

        except TypeError:
            try:
                result = MainApp.service_callback(service_name, request_data)
                if result is None:
                    return True
                return bool(result)
            except Exception as e:
                print(f"[UI] 서비스 호출 실패({service_name}): {e}")
                return False

        except Exception as e:
            print(f"[UI] 서비스 호출 실패({service_name}): {e}")
            return False

    def request_error_response(self, action_code, response_callback=None):
        return self.request_service(
            SystemConfig.SERVICE_ERROR_RESPONSE,
            {"code": int(action_code)},
            response_callback
        )

    def request_emergency_stop(self):
        """
        현재 컨트롤 코드에는 UI -> Controller 비상정지 전용 서비스가 없다.
        따라서 UI 버튼은 누락된 /emergency_stop 서비스를 호출하지 않고,
        Controller -> UI /ui/error_notify(code=3)를 받은 것과 동일하게
        비상정지 안내창을 띄운다.

        실제 로봇 비상정지는 컨트롤러/안전입력 쪽에서 처리하고,
        이후 사용자의 수동제어/초기화 선택만 /controller/error_response로 보낸다.
        """
        self.trigger_exception_stop(3)
        return True

    def normalize_service_response(self, response):
        if response is None:
            return {}

        if isinstance(response, dict):
            data = dict(response)

        elif isinstance(response, str):
            try:
                import json
                parsed = json.loads(response)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"message": response}
            except Exception:
                if response.strip() in ["0", "1"]:
                    data = {"result": int(response.strip())}
                else:
                    data = {"message": response}

        elif isinstance(response, bool):
            data = {
                "result": (
                    SystemConfig.SERVICE_ACCEPT
                    if response
                    else SystemConfig.SERVICE_REJECT
                ),
                "success": bool(response)
            }

        elif isinstance(response, int):
            data = {"result": response}

        else:
            data = {}
            for key in [
                "result", "response", "response_code", "service_result",
                "status", "decision", "accepted", "success", "message",
                "book_info", "book", "current_book", "data",
                "event_code", "exception_code", "status_code", "code"
            ]:
                if hasattr(response, key):
                    data[key] = getattr(response, key)

        result = self.extract_service_result(data)

        if result is not None:
            data["result"] = result
            data["accepted"] = result == SystemConfig.SERVICE_ACCEPT
            data["success"] = result == SystemConfig.SERVICE_ACCEPT

        elif "success" in data:
            success = bool(data.get("success"))
            data["result"] = (
                SystemConfig.SERVICE_ACCEPT
                if success
                else SystemConfig.SERVICE_REJECT
            )
            data["accepted"] = success

        return data

    def extract_service_result(self, response):
        # code 필드는 예외 정지 코드/오류대응 요청 코드와 충돌하므로 결과값으로 해석하지 않는다.
        for key in [
            "result", "response", "response_code", "service_result",
            "status", "decision", "accepted"
        ]:
            if key not in response:
                continue

            value = response.get(key)
            parsed = self.parse_service_result_value(value)
            if parsed is not None:
                return parsed

        return None

    def parse_service_result_value(self, value):
        if isinstance(value, bool):
            return (
                SystemConfig.SERVICE_ACCEPT
                if value
                else SystemConfig.SERVICE_REJECT
            )

        if isinstance(value, int):
            if value in [SystemConfig.SERVICE_ACCEPT, SystemConfig.SERVICE_REJECT]:
                return value
            return None

        if isinstance(value, str):
            text = value.strip().lower()

            if text == "0":
                return SystemConfig.SERVICE_ACCEPT

            if text == "1":
                return SystemConfig.SERVICE_REJECT

            if text in [
                "ok", "accept", "accepted", "true",
                "success", "확인", "성공"
            ]:
                return SystemConfig.SERVICE_ACCEPT

            if text in [
                "reject", "rejected", "false",
                "fail", "failed", "거절", "실패"
            ]:
                return SystemConfig.SERVICE_REJECT

        return None

    def is_service_rejected(self, response):
        response = self.normalize_service_response(response)
        return response.get("result") == SystemConfig.SERVICE_REJECT

    def is_service_accepted(self, response):
        response = self.normalize_service_response(response)
        return response.get("result") == SystemConfig.SERVICE_ACCEPT

    def extract_book_data(self, response):
        if response is None:
            return None

        if isinstance(response, str):
            try:
                import json
                response = json.loads(response)
            except Exception:
                return None

        if isinstance(response, (list, tuple)):
            return list(response)

        response = self.normalize_service_response(response)

        if response.get("result") == SystemConfig.SERVICE_REJECT:
            return None

        for key in ["book_info", "book", "current_book", "data"]:
            value = response.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return value

        if "title" in response or "book_id" in response or "dimensions" in response:
            return response

        return None

    def clear_book_display(self, *args):
        self.book_info_display.setText("📖 현재 분류 중인 도서 정보 없음")
        return True

    def update_book_display(self, book_list):
        book_data = self.extract_book_data(book_list)
        if book_data is not None:
            book_list = book_data

        if not book_list:
            self.clear_book_display()
            return False

        if isinstance(book_list, dict):
            current_book = book_list
        elif isinstance(book_list, (list, tuple)):
            current_book = next(
                (book for book in book_list if isinstance(book, dict)),
                None
            )
            if current_book is None:
                self.clear_book_display()
                return False
        else:
            self.clear_book_display()
            return False

        def first_value(data, keys, default="-"):
            for key in keys:
                value = data.get(key)
                if value not in [None, ""]:
                    return value
            return default

        def number_value(value, default=0.0):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        dimensions = current_book.get("dimensions", {})

        if isinstance(dimensions, dict):
            width_mm = number_value(first_value(
                dimensions,
                ["width", "w", "size_w", "book_width"],
                0
            ))
            length_mm = number_value(first_value(
                dimensions,
                ["length", "height", "h", "size_h", "book_length"],
                0
            ))
            thickness_mm = number_value(first_value(
                dimensions,
                ["thickness", "depth", "d", "size_d", "book_thickness"],
                0
            ))

        elif isinstance(dimensions, (list, tuple)) and len(dimensions) >= 3:
            width_mm = number_value(dimensions[0])
            length_mm = number_value(dimensions[1])
            thickness_mm = number_value(dimensions[2])

        else:
            width_mm = number_value(first_value(
                current_book,
                ["width", "w", "size_w", "book_width"],
                0
            ))
            length_mm = number_value(first_value(
                current_book,
                ["length", "height", "h", "size_h", "book_length"],
                0
            ))
            thickness_mm = number_value(first_value(
                current_book,
                ["thickness", "depth", "d", "size_d", "book_thickness"],
                0
            ))

        width = width_mm / 10
        length = length_mm / 10
        thickness = thickness_mm / 10

        qr_code = first_value(current_book, ["qr_code", "qr", "book_id"], "-")
        book_id = first_value(current_book, ["book_id", "id"], "-")
        title = first_value(current_book, ["title", "name", "book_name"], "알 수 없음")
        section = first_value(
            current_book,
            ["target_location", "section", "shelf", "target_section", "location"],
            "-"
        )

        self.book_info_display.setText(
            f"📖 현재 분류 중인 도서 정보\n──────────────────\n"
            f"■ 제목: {title}\n"
            f"■ 도서 ID: {book_id}\n"
            f"■ 섹션: 섹션 {section}\n"
            f"■ 크기: {width:.1f} x {length:.1f} x {thickness:.1f} cm\n"
            f"■ QR: {qr_code}"
        )

        return True

    def clear_camera_viewer(self):
        if hasattr(self, "camera_clear_timer"):
            self.camera_clear_timer.stop()

        self.cam_view.clear()
        self.cam_view.setPixmap(QPixmap())
        self.cam_view.setText(SystemConfig.CAMERA_WAITING_TEXT)
        self.cam_view.setStyleSheet(SystemConfig.CAMERA_BLACK_STYLE)

    def update_camera_viewer(self, camera_frame):
        try:
            if camera_frame is None:
                self.clear_camera_viewer()
                return

            if not hasattr(camera_frame, "size") or camera_frame.size == 0:
                self.clear_camera_viewer()
                return

            if len(camera_frame.shape) != 3 or camera_frame.shape[2] != 3:
                self.clear_camera_viewer()
                return

            try:
                import numpy as np
                camera_frame = np.ascontiguousarray(camera_frame)
            except Exception:
                pass

            height, width, channel = camera_frame.shape

            q_img = QImage(
                camera_frame.data,
                width,
                height,
                channel * width,
                QImage.Format.Format_RGB888
            ).rgbSwapped().copy()

            pixmap = QPixmap.fromImage(q_img)
            target_size = self.cam_view.contentsRect().size()

            if target_size.width() <= 0 or target_size.height() <= 0:
                return

            scaled_pixmap = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            self.cam_view.setText("")
            self.cam_view.setPixmap(scaled_pixmap)

            if hasattr(self, "camera_clear_timer"):
                self.camera_clear_timer.start()

        except Exception:
            self.clear_camera_viewer()


    def trigger_exception_stop(self, code):
        try:
            code = int(code)
        except (TypeError, ValueError):
            return

        if code not in SystemConfig.EXCEPTION_STOP_MSG:
            return

        if self.exception_dialog is not None and self.exception_dialog.isVisible():
            return

        self.exception_dialog = ExceptionStopDialog(code, self, self)
        self.exception_dialog.exec()


    def go_to_work_slide(self):
        self.clear_camera_viewer()
        self.clear_book_display()
        self.set_task_reset_button_enabled(False)
        self.stacked_widget.setCurrentIndex(1)

        self.request_classification_start(
            return_to_start_on_fail=True,
            keep_reset_enabled_on_fail=False
        )

    def request_classification_start(
        self,
        return_to_start_on_fail=False,
        keep_reset_enabled_on_fail=True
    ):
        sent = self.request_service(
            SystemConfig.SERVICE_SORT_REQUEST,
            {},
            None
        )

        if not sent:
            QMessageBox.critical(
                self,
                "서비스 오류",
                "컨트롤러 cleanup_request 서비스를 호출하지 못했습니다."
            )

            if return_to_start_on_fail:
                self.stacked_widget.setCurrentIndex(0)

            self.set_task_reset_button_enabled(keep_reset_enabled_on_fail)
            return False

        self.set_task_reset_button_enabled(False)

        if hasattr(self, "work_status_label"):
            self.work_status_label.setText("📚 분류 작업 진행 중")

        return True

    def handle_task_complete(self, *args):
        """
        Controller가 /ui/task_complite를 호출하면 ui_node.py에서
        clear_book_signal을 발생시킨다.

        이 신호를 받으면 작업 화면은 유지하고,
        현재 도서/카메라 표시를 초기화한 뒤 테스크 초기화 버튼을 활성화한다.
        """
        self.clear_book_display()
        self.clear_camera_viewer()
        self.stacked_widget.setCurrentIndex(1)
        self.set_task_reset_button_enabled(True)

        if hasattr(self, "work_status_label"):
            self.work_status_label.setText("✅ 작업 완료 - 테스크 초기화 후 분류를 재개하세요")

        return True

    def restart_classification_after_complete(self):
        """
        작업 완료 후 사용자가 테스크 초기화 버튼을 누르면
        다시 /controller/cleanup_request를 보내 다음 분류 작업을 시작한다.
        """
        self.clear_camera_viewer()
        self.clear_book_display()
        self.request_classification_start(
            return_to_start_on_fail=False,
            keep_reset_enabled_on_fail=True
        )

    def set_task_reset_button_enabled(self, enabled):
        if not hasattr(self, "task_reset_btn"):
            return

        enabled = bool(enabled)
        self.task_reset_btn.setEnabled(enabled)

        if enabled:
            self.task_reset_btn.setText("🔄 테스크 초기화 / 분류 재개")
            self.task_reset_btn.setStyleSheet(
                "padding: 12px; font-weight: bold; "
                "background-color: #e3f2fd; color: black;"
            )
        else:
            self.task_reset_btn.setText("🔄 테스크 초기화")
            self.task_reset_btn.setStyleSheet(
                "padding: 12px; font-weight: bold; "
                "background-color: #f5f5f5; color: #777;"
            )



    def handle_exit_request(self):
        self.close()


    def open_registration_popup(self):
        dialog = BookRegistrationDialog(self)

        if dialog.exec() and hasattr(dialog, "registered_data"):
            if self.db_manager is None or getattr(self.db_manager, "books", None) is None:
                QMessageBox.warning(
                    self,
                    "DB 연결 안됨",
                    "데이터베이스 연결 상태를 확인하세요."
                )
                return

            try:
                data = dialog.registered_data
                w_cm, h_cm, d_cm = data["dimensions"]

                new_book_doc = self.db_manager.insert_new_book(
                    title=data["title"],
                    width=w_cm * 10,
                    length=h_cm * 10,
                    thickness=d_cm * 10,
                    section=data["section"]
                )

                if new_book_doc:
                    self.show_qr_popup(new_book_doc)
                else:
                    QMessageBox.critical(
                        self,
                        "DB 저장 실패",
                        "도서 정보를 저장하지 못했습니다."
                    )

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "DB 연동 오류",
                    f"도서 등록 실패: {e}"
                )

    def show_qr_popup(self, doc_data):
        qr_code = doc_data.get("qr_code", doc_data.get("book_id"))

        QRDisplayDialog(
            doc_data["book_id"],
            doc_data["title"],
            qr_code,
            self
        ).exec()


    def trigger_emergency_stop(self):
        sent = self.request_emergency_stop()

        if not sent:
            QMessageBox.critical(
                self,
                "서비스 오류",
                "비상정지 서비스를 호출하지 못했습니다."
            )
            return

        if hasattr(self, "work_status_label"):
            self.work_status_label.setText("🚨 비상정지 알림 표시")

    def update_top_bar(self, index):
        self.mergency_btn.hide()
        # if index in [0, 2]:
        #     self.emergency_btn.hide()
        # else:
        #     self.emergency_btn.show()

    def closeEvent(self, event):
        if hasattr(self, "camera_clear_timer"):
            self.camera_clear_timer.stop()

        super().closeEvent(event)


def create_ui(ui_node=None, db_manager=None):
    app = QApplication.instance() or QApplication(sys.argv)

    main_win = MainApp(db_manager=db_manager)

    if ui_node is not None:
        main_win.set_ros_node(ui_node)

    main_win.show()

    return app, main_win


def show_ui(ui_node=None, db_manager=None):
    app, main_win = create_ui(ui_node, db_manager)
    return app.exec()


import sys
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QStackedWidget, QPushButton, QLabel, 
                             QDialog, QLineEdit, QFormLayout, QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap

# ==============================================================================
# [중요] 백엔드 연동 설정 및 데이터 구조화
# ==============================================================================
class SystemConfig:
    # 💡 나중에 백엔드와 약속한 에러 코드가 생기면 이 부분을 직접 수정/추가해 주시면 됩니다.
    WARNING_MSG = {
        "W-001": "⚠️ 반납대에 이물질이 감지되었습니다.",
        "W-002": "⚠️ QR 코드 크기가 너무 작아 인식이 불가능합니다."
    }
    ERROR_MSG = {
        "E-001": "❌ 고정 카메라 연결이 끊어졌습니다. 통신 오류!",
        "E-002": "❌ 로봇 하드웨어 이상이 발생했습니다."
    }

    SIZE_LIMITS = {
        "max_w": 30.0, "max_h": 20.0, "max_d": 5.0,
        "min_w": 15.0, "min_h": 10.0, "min_d": 2.0
    }

    # 글로벌 도서 데이터 일괄 관리를 위한 컬렉션 리스트 모델 변수
    book_list = []


# ---------------------------------------------------
# [인터페이스 전용] 시스템 컨트롤 가상 시그널 브릿지 클래스
# ---------------------------------------------------
class SystemControlBridge(QObject):
    """ 컨트롤단(백엔드) 개발자가 이 시그널들을 통해 UI 메인 화면으로 데이터를 밀어줍니다. """
    frame_received = pyqtSignal(np.ndarray)               # OpenCV 이미지 스트리밍용 (.emit() 호출)
    book_data_received = pyqtSignal(list)                 # 현재 작업중인 책 정보 동기화용 (.emit() 호출)
    hardware_status_changed = pyqtSignal(str, str)        # 로봇, 카메라 상태 제어 및 화면 전환용 (.emit() 호출)
    exception_triggered = pyqtSignal(str)                 # 원격 에러 코드 및 복구 완료(HOME_DONE) 신호용 (.emit() 호출)

# 글로벌 공유 인스턴스 (컨트롤 단 개발자가 소통 링크로 가져다 쓸 객체)
bridge = SystemControlBridge()


# ---------------------------------------------------
# [팝업 창] 신규 도서 등록 다이얼로그
# ---------------------------------------------------
class BookRegistrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("신규 도서 등록")
        self.setFixedSize(360, 280)
        
        layout = QFormLayout(self)
        self.name_input = QLineEdit(self)
        
        self.author_input = QLineEdit(self)
        self.author_input.setPlaceholderText("저자 이름 입력")

        self.shelf_input = QLineEdit(self)
        self.shelf_input.setValidator(QIntValidator(1, 4, self))
        self.shelf_input.setPlaceholderText("배정할 섹션 번호 (1~4)")
        
        self.size_w_input = QLineEdit(self)
        self.size_h_input = QLineEdit(self)
        self.size_d_input = QLineEdit(self)
        
        double_validator = QDoubleValidator(0.0, 99.9, 2, self)
        double_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        
        self.size_w_input.setValidator(double_validator)
        self.size_h_input.setValidator(double_validator)
        self.size_d_input.setValidator(double_validator)
        
        self.size_w_input.setPlaceholderText("가로(W)")
        self.size_h_input.setPlaceholderText("세로(H)")
        self.size_d_input.setPlaceholderText("두께(D)")
        
        size_layout = QHBoxLayout()
        size_layout.addWidget(self.size_w_input)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.size_h_input)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.size_d_input)
        
        layout.addRow("도서 이름:", self.name_input)
        layout.addRow("작가:", self.author_input)
        layout.addRow("배정 섹션:", self.shelf_input)
        layout.addRow("사이즈 (cm):", size_layout)
        
        self.reg_btn = QPushButton("등록 및 QR 생성", self)
        self.reg_btn.clicked.connect(self.handle_registration)
        layout.addWidget(self.reg_btn)
        
    def handle_registration(self):
        name = self.name_input.text().strip()
        author = self.author_input.text().strip()
        shelf_id = self.shelf_input.text().strip()
        w_str = self.size_w_input.text().strip()
        h_str = self.size_h_input.text().strip()
        d_str = self.size_d_input.text().strip()
        
        if not name or not author or not shelf_id or not w_str or not h_str or not d_str:
            QMessageBox.warning(self, "입력 오류", "모든 칸을 입력해 주세요.")
            return False
            
        w, h, d = float(w_str), float(h_str), float(d_str)
        
        limits = SystemConfig.SIZE_LIMITS
        if (w > limits["max_w"] or h > limits["max_h"] or d > limits["max_d"] or
            w < limits["min_w"] or h < limits["min_h"] or d < limits["min_d"]):
            
            QMessageBox.critical(
                self, "규격 초과/미달 (거절)", 
                f"도서 크기가 허용 범위를 벗어나 등록할 수 없습니다.\n\n"
                f"허용 최대: {limits['max_w']} x {limits['max_h']} x {limits['max_d']}\n"
                f"허용 최소: {limits['min_w']} x {limits['min_h']} x {limits['min_d']}\n\n"
                f"입력 크기: {w} x {h} x {d}"
            )
            return False
            
        # 정제된 딕셔너리 데이터를 인스턴스에 안전하게 저장하여 MainApp으로 토스
        self.registered_data = {
            "title": name,
            "author": author,
            "shelf_id": int(shelf_id),
            "size": {"width": w, "height": h, "depth": d}
        }
        self.accept()
        return True


# ---------------------------------------------------
# [팝업 창] 로봇 복구 진행 알림 다이얼로그
# ---------------------------------------------------
class MovingToHomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로봇 복구 중")
        self.setFixedSize(350, 120)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        self.lbl = QLabel("🤖 로봇이 초기 위치로 이동중입니다...", alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl)
        
        self.pbar = QProgressBar(self)
        self.pbar.setRange(0, 0) # 무한 롤링 바 상태 유지
        layout.addWidget(self.pbar)


# ---------------------------------------------------
# [팝업 창] 시스템 경고 다이얼로그
# ---------------------------------------------------
class WarningDialog(QDialog):
    def __init__(self, code, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.setWindowTitle("시스템 경고")
        self.setFixedSize(400, 200)
        layout = QVBoxLayout(self)
        
        title = QLabel("⚠️ SYSTEM WARNING", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; color: orange; font-weight: bold;")
        layout.addWidget(title)
        
        msg = SystemConfig.WARNING_MSG.get(code, "경고")
        content = QLabel(f"코드: {code}\n\n{msg}", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(content)
        
        btn = QPushButton("🔄 장치 원위치 복구 및 시스템 재기동", self)
        btn.setStyleSheet("color: black; font-weight: bold; padding: 6px;")
        btn.clicked.connect(self.handle_click)
        layout.addWidget(btn)

    def handle_click(self):
        success = self.main_app.run_recovery_sequence()
        if success:
            self.accept()


# ---------------------------------------------------
# [팝업 창] 치명 오류 다이얼로그
# ---------------------------------------------------
class ErrorDialog(QDialog):
    def __init__(self, code, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.setWindowTitle("치명 오류 발생")
        self.setFixedSize(400, 200)
        layout = QVBoxLayout(self)
        
        title = QLabel("❌ CRITICAL ERROR", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; color: red; font-weight: bold;")
        layout.addWidget(title)
        
        msg = SystemConfig.ERROR_MSG.get(code, "오류")
        content = QLabel(f"코드: {code}\n\n{msg}", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(content)
        
        btn = QPushButton("🔄 복구 작업 수행 후 장치 재가동", self)
        btn.setStyleSheet("color: black; font-weight: bold; padding: 6px;")
        btn.clicked.connect(self.handle_click)
        layout.addWidget(btn)

    def handle_click(self):
        success = self.main_app.run_recovery_sequence()
        if success:
            self.accept()


# ---------------------------------------------------
# [팝업 창] 비상 정지 다이얼로그
# ---------------------------------------------------
class EmergencyDialog(QDialog):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.setWindowTitle("비상 정지 상태")
        self.setFixedSize(450, 220)
        layout = QVBoxLayout(self)
        
        title = QLabel("🚨 HARDWARE EMERGENCY STOP", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; color: red; font-weight: bold; background-color: #330000; padding: 5px;")
        layout.addWidget(title)
        
        content = QLabel("사용자 입력 또는 하드웨어 비상 신호에 의해 동작이 정지되었습니다.\n안전을 확보한 후 시스템 복구를 수행하십시오.", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(content)
        
        btn = QPushButton("🔄 비상정지 해제 및 하드웨어 초기화", self)
        btn.setStyleSheet("font-size: 14px; padding: 8px; background-color: #e0f2f1; color: black; font-weight: bold;")
        btn.clicked.connect(self.handle_click)
        layout.addWidget(btn)

    def handle_click(self):
        success = self.main_app.run_recovery_sequence()
        if success:
            self.accept()


# ---------------------------------------------------
# [메인 애플리케이션] 전체 슬라이드 관리 및 제어 흐름 바인딩
# ---------------------------------------------------
class MainApp(QMainWindow):
    # 컨트롤 단에서 건네받을 실행 함수(콜백 변수) 상자
    command_callback = None

    @classmethod
    def register_command_callback(cls, func):
        """ 컨트롤 단 개발자가 이 함수를 호출해 진짜 백엔드 제어 기능을 UI에 심어둡니다. """
        cls.command_callback = func

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Book Binder Control System")
        self.setGeometry(100, 100, 900, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # [상단 고정 바] 비상정지 및 종료
        top_bar = QHBoxLayout()
        self.emergency_btn = QPushButton("🚨 비상 정지", self)
        self.emergency_btn.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 8px;")
        self.emergency_btn.clicked.connect(self.trigger_emergency_stop)
        top_bar.addWidget(self.emergency_btn)
        
        top_bar.addStretch()
        
        self.exit_btn = QPushButton("❌ 종료", self)
        self.exit_btn.setStyleSheet("padding: 8px;")
        self.exit_btn.clicked.connect(self.handle_exit_request)
        top_bar.addWidget(self.exit_btn)
        main_layout.addLayout(top_bar)

        # [중앙 스택 위젯] 3개의 슬라이드 유지 (시작 -> 로딩 -> 메인작업)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self.init_slides()

        self.stacked_widget.setCurrentIndex(0)
        self.update_top_bar(0)
        self.stacked_widget.currentChanged.connect(self.update_top_bar)

        self.is_hardware_on = False  
        self.moving_dialog = None  

        # 💡 [출력 연동 완성] bridge 시그널이 발생할 때 화면을 갱신할 수 있도록 리스너 함수 매핑 완료
        bridge.frame_received.connect(self.update_camera_viewer)
        bridge.book_data_received.connect(self.update_book_display)
        bridge.hardware_status_changed.connect(self.update_hardware_status)
        bridge.exception_triggered.connect(self.handle_remote_exception)

    def init_slides(self):
        # 1. 메인 시작 화면
        slide_start = QWidget()
        l1 = QVBoxLayout(slide_start)
        title = QLabel("📚 도서 관리 시스템", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 20px;")
        l1.addWidget(title)
        
        start_btn = QPushButton("시작")
        start_btn.setStyleSheet("font-size: 16px; padding: 15px;")
        start_btn.clicked.connect(self.go_to_loading_slide)
        l1.addWidget(start_btn)
        self.stacked_widget.addWidget(slide_start)

        # 2. 로딩 및 장치 기동 제어 화면
        slide_load = QWidget()
        l2 = QVBoxLayout(slide_load)
        
        led_layout = QHBoxLayout()
        led_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        led_layout.setSpacing(40) 
        
        self.led_style_red = "background-color: red; border-radius: 10px; min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;"
        self.led_style_green = "background-color: limegreen; border-radius: 10px; min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;"
        
        self.robot_led = QLabel(self)
        self.robot_led.setStyleSheet(self.led_style_red)
        self.robot_txt = QLabel("로봇 OFFLINE", self)
        self.robot_txt.setStyleSheet("font-size: 14px;")
        led_layout.addWidget(self.robot_led)
        led_layout.addWidget(self.robot_txt)
        
        self.cam_led = QLabel(self)
        self.cam_led.setStyleSheet(self.led_style_red)
        self.cam_txt = QLabel("카메라 OFFLINE", self)
        self.cam_txt.setStyleSheet("font-size: 14px;")
        led_layout.addWidget(self.cam_led)
        led_layout.addWidget(self.cam_txt)
        
        l2.addLayout(led_layout)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        l2.addWidget(self.progress_bar)
        
        self.classify_start_btn = QPushButton("로봇 & 카메라 장치 기동 시작", self)
        self.classify_start_btn.setStyleSheet("font-size: 16px; padding: 12px; font-weight: bold;")
        self.classify_start_btn.clicked.connect(self.start_device_loading)
        l2.addWidget(self.classify_start_btn)
        
        self.stacked_widget.addWidget(slide_load)

        # 3. 메인 작업 화면
        slide_work = QWidget()
        l3_main = QVBoxLayout(slide_work)
        
        upper_layout = QHBoxLayout()
        
        self.cam_view = QLabel("📷 실시간 카메라 화면\n(영상 수신 대기 중 - 검은 화면)", alignment=Qt.AlignmentFlag.AlignCenter)
        self.cam_view.setStyleSheet("background-color: black; color: #aaaaaa; font-size: 14px; border: 2px solid #333;")
        upper_layout.addWidget(self.cam_view, stretch=1)
        
        right_part = QVBoxLayout()
        self.work_status_label = QLabel("🤖 장치 가동 완료 - 정상 운영 중", self)
        self.work_status_label.setStyleSheet("color: green; font-weight: bold; font-size: 14px;")
        right_part.addWidget(self.work_status_label)
        
        self.book_info_display = QLabel("📖 현재 분류 중인 도서 정보 없음", self)
        self.book_info_display.setStyleSheet("background-color: #f9f9f9; padding: 15px; border-radius: 5px; font-size: 13px; color: black;")
        right_part.addWidget(self.book_info_display)
        
        right_part.addStretch()
        
        reg_popup_btn = QPushButton("➕ 신규 책 등록")
        reg_popup_btn.setStyleSheet("padding: 12px; font-weight: bold; background-color: #e1f5fe; color: black;")
        reg_popup_btn.clicked.connect(self.open_registration_popup)
        right_part.addWidget(reg_popup_btn)
        
        upper_layout.addLayout(right_part, stretch=1)
        l3_main.addLayout(upper_layout)
        
        self.stacked_widget.addWidget(slide_work)

    # ---------------------------------------------------
    # 입력 방향: UI ➔ 컨트롤러 제어 요청 송신 통로
    # ---------------------------------------------------
    def send_device_command(self, command_type, data=None):
        """ 버튼 등이 눌렸을 때 컨트롤단에 주입받은 함수로 명령과 인자를 안전하게 패스합니다. """
        print(f"[UI ➡️ 컨트롤 단] 제어 명령 송신: {command_type}")
        if MainApp.command_callback is not None:
            if data is not None:
                MainApp.command_callback((command_type, data))
            else:
                MainApp.command_callback(command_type)
            return True
        return False

    # ---------------------------------------------------
    # 출력 방향: 컨트롤러 ➔ UI 실시간 데이터 표출 인터페이스
    # ---------------------------------------------------
    def update_book_display(self, book_list):
        """ 💡 컨트롤 단에서 책 정보 목록 수신 시, 우측 현재 작업도서 패널에 텍스트를 자동 표출합니다. """
        if not book_list:
            self.book_info_display.setText("📖 현재 분류 중인 도서 정보 없음")
            return False
            
        current_book = book_list[0]
        title = current_book.get("title", "알 수 없음")
        author = current_book.get("author", "알 수 없음")
        shelf_id = current_book.get("shelf_id", "-")
        size = current_book.get("size", {"width": 0, "height": 0, "depth": 0})
        
        self.book_info_display.setText(
            f"📖 현재 분류 중인 도서 정보\n"
            f"──────────────────\n"
            f"■ 제목: {title}\n"
            f"■ 작가: {author}\n"
            f"■ 섹션: 섹션 {shelf_id}\n"
            f"■ 사이즈: {size['width']} x {size['height']} x {size['depth']} cm"
        )
        return True

    def update_hardware_status(self, robot_status, camera_status):
        """ 💡 컨트롤 단에서 장치 상태 수신 시, LED 색상을 변경하고 둘 다 ONLINE 완료 시 메인 작업 창으로 자동 전환합니다. """
        if robot_status == "ONLINE":
            self.robot_led.setStyleSheet(self.led_style_green)
            self.robot_txt.setText("로봇 ONLINE")
            self.is_hardware_on = True
        else:
            self.robot_led.setStyleSheet(self.led_style_red)
            self.robot_txt.setText(f"로봇 {robot_status}")
            self.is_hardware_on = False

        if camera_status == "ONLINE":
            self.cam_led.setStyleSheet(self.led_style_green)
            self.cam_txt.setText("카메라 ONLINE")
        else:
            self.cam_led.setStyleSheet(self.led_style_red)
            self.cam_txt.setText(f"카메라 {camera_status}")

        # 두 물리 하드웨어 기동 성공 시 다음 작업화면(스택 인덱스 2)으로 전환 처리
        if robot_status == "ONLINE" and camera_status == "ONLINE":
            self.exit_btn.setEnabled(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.stacked_widget.setCurrentIndex(2)

    def update_camera_viewer(self, camera_frame):
        """ 💡 컨트롤 단에서 OpenCV 영상 수신 시, PyQt 픽스맵 포맷 채널 변환 후 모니터링 영역에 출력합니다. """
        try:
            if camera_frame is None or camera_frame.size == 0:
                return
            
            height, width, channel = camera_frame.shape
            bytes_per_line = channel * width
            q_img = QImage(camera_frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()
            
            pixmap = QPixmap.fromImage(q_img)
            scaled_pixmap = pixmap.scaled(self.cam_view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.cam_view.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"영상 스트리밍 변환 예외: {e}")

    def handle_remote_exception(self, code):
        """ 💡 컨트롤 단에서 비동기 예외 코드 수신 시 전용 경고창을 연동하고, 복귀 완료(HOME_DONE) 수신 시 진행 팝업을 닫습니다. """
        if code in SystemConfig.WARNING_MSG:
            self.trigger_warning(code)
        elif code in SystemConfig.ERROR_MSG:
            self.trigger_error(code)
        elif code == "HOME_DONE":
            # 컨트롤단으로부터 로봇 복귀 시퀀스 최종 종료 신호를 받으면 열려 있던 대기창 닫기
            if self.moving_dialog:
                self.moving_dialog.accept()
        else:
            self.trigger_emergency_stop()

    # ---------------------------------------------------
    # 화면 제어 및 인터랙션 매핑
    # ---------------------------------------------------
    def go_to_loading_slide(self):
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 100)
        self.classify_start_btn.setEnabled(True)
        self.stacked_widget.setCurrentIndex(1)

    def start_device_loading(self):
        self.exit_btn.setEnabled(False)
        self.classify_start_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0) # 무한 지연 상태 인디케이터
        
        # 컨트롤 단에 디바이스 가동을 요청
        self.send_device_command("START_DEVICES")

    def run_recovery_sequence(self):
        reply = QMessageBox.question(
            self, '초기 위치 원위치 복구', 
            "정말로 초기 위치로 되돌리겠습니까?\n(주변 이물질을 모두 제거하였는지 확인해 주십시오)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cam_view.clear()
            self.cam_view.setText("📷 실시간 카메라 화면\n(영상 수신 대기 중 - 검은 화면)")
            self.cam_view.setStyleSheet("background-color: black; color: #aaaaaa; font-size: 14px; border: 2px solid #333;")
            self.book_info_display.setText("📖 현재 분류 중인 도서 정보 없음")
            
            # 원위치 이동 대기 다이얼로그 모달 실행
            self.moving_dialog = MovingToHomeDialog(self)
            
            # 컨트롤단으로 원위치 리셋 신호 송신
            self.send_device_command("MOVE_HOME")
            
            # 다이얼로그 실행 (백엔드가 bridge를 통해 HOME_DONE 코드를 날려 .accept() 시켜줄 때까지 유지)
            self.moving_dialog.exec()
            
            QMessageBox.information(self, '초기화 완료', "초기화 완료, '확인'버튼 누르면 다시 카메라 있던 창으로 복귀합니다.")
            self.stacked_widget.setCurrentIndex(2) 
            return True
            
        return False 

    def handle_exit_request(self):
        reply = QMessageBox.question(self, '종료 확인', '정말로 종료하시겠습니까?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.is_hardware_on or self.stacked_widget.currentIndex() == 2:
                self.stacked_widget.setCurrentIndex(1) 
                self.exit_btn.setEnabled(False)
                self.progress_bar.setRange(0, 0)
                self.send_device_command("STOP_DEVICES")
            else:
                self.close()

    def open_registration_popup(self):
        dialog = BookRegistrationDialog(self)
        if dialog.exec():
            if hasattr(dialog, 'registered_data'):
                # 사용자가 폼에 입력 완료 시, 컨트롤단에 딕셔너리 구조를 통째로 전달
                self.send_device_command("REGISTER_NEW_BOOK", data=dialog.registered_data)

    def trigger_warning(self, code):
        dialog = WarningDialog(code, self, self)
        dialog.exec()

    def trigger_error(self, code):
        dialog = ErrorDialog(code, self, self)
        dialog.exec()

    def trigger_emergency_stop(self):
        self.send_device_command("EMERGENCY")
        dialog = EmergencyDialog(self, self)
        dialog.exec()

    def update_top_bar(self, index):
        if index in [0, 1]:
            self.emergency_btn.hide()
        else:
            self.emergency_btn.show()


def show_ui():
    """다른 파일에서 ui_1.show_ui()로 호출하여 UI를 즉시 실행할 수 있는 진입점 함수"""
    import sys
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        
    main_win = MainApp()
    main_win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    show_ui()
import sys
import threading
import importlib

import rclpy
from rclpy.node import Node

from std_srvs.srv import Empty, Trigger
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from app.ui.ui_1 import create_ui
except Exception:
    from ui_1 import create_ui


try:
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    IMAGE_STREAM_AVAILABLE = True
except ImportError:
    Image = None
    CvBridge = None
    IMAGE_STREAM_AVAILABLE = False


SERVICE_ACCEPT = 0
SERVICE_REJECT = 1

# ============================================================
# Interface names - Controller code 기준으로 고정
# ============================================================

# UI -> Controller
CLEANUP_REQUEST_SERVICE_NAME = "/controller/cleanup_request"
ERROR_RESPONSE_SERVICE_NAME = "/controller/error_response"

# Controller -> UI
UI_ERROR_NOTIFY_SERVICE_NAME = "/ui/error_notify"
UI_TASK_COMPLETE_SERVICE_NAME = "/ui/task_complite"  # Controller 코드의 오타 이름 그대로 유지

# Optional / existing DB lookup interface
BOOK_DETECTED_SERVICE_NAME = "/book_detected"

# Camera -> UI
CAMERA_IMAGE_TOPIC_NAME = "/camera/image_raw"

# Custom srv package
CUSTOM_SRV_MODULE = "interfaces.srv"
UI_ERROR_RESPONSE_SRV_CLASS = "UiErrorResponse"
UI_ERROR_NOTIFY_SRV_CLASS = "UiErrorNotify"
BOOK_DETECTED_SRV_CLASS = "BookDetected"

# 기존 테스트 srv가 남아있는 환경에서도 최소한 실행되도록 하는 fallback
LEGACY_CODE_COMMAND_SRV_CLASS = "CodeCommand"


# ============================================================
# Dynamic service loading
# ============================================================

def load_srv_type(class_name, *, quiet=False):
    try:
        module = importlib.import_module(CUSTOM_SRV_MODULE)
        return getattr(module, class_name)

    except Exception as e:
        if not quiet:
            print(
                f"[UI_NODE] srv import failed: "
                f"{CUSTOM_SRV_MODULE}.{class_name} / {e}"
            )
        return None


def load_srv_type_with_fallback(primary_class_name, fallback_class_name=None):
    srv_type = load_srv_type(primary_class_name)

    if srv_type is not None:
        return srv_type

    if fallback_class_name is None:
        return None

    fallback_type = load_srv_type(fallback_class_name, quiet=True)

    if fallback_type is not None:
        print(
            f"[UI_NODE] {primary_class_name}을 찾지 못해 "
            f"{fallback_class_name}으로 임시 fallback합니다. "
            f"컨트롤 코드와 통합할 때는 {primary_class_name}.srv 타입을 맞추는 것이 정석입니다."
        )

    return fallback_type


class UISignalBridge(QObject):
    camera_frame_signal = pyqtSignal(object)

    book_info_signal = pyqtSignal(object)
    clear_book_signal = pyqtSignal()

    exception_stop_signal = pyqtSignal(object)

    # ROS thread -> Qt main thread
    service_response_signal = pyqtSignal(object, object)

    def __init__(self):
        super().__init__()
        self.service_response_signal.connect(self.dispatch_service_response)

    def dispatch_service_response(self, response_callback, response_data):
        if response_callback is not None:
            response_callback(response_data)


class UINode(Node):
    def __init__(self, db_manager=None):
        super().__init__("book_binder_ui_node")

        self.db_manager = db_manager
        self.signal_bridge = UISignalBridge()

        # ui_1.py 연결용 PyQt signals
        self.camera_frame_signal = self.signal_bridge.camera_frame_signal
        self.book_info_signal = self.signal_bridge.book_info_signal
        self.clear_book_signal = self.signal_bridge.clear_book_signal
        self.exception_stop_signal = self.signal_bridge.exception_stop_signal

        # Custom service types
        self.ui_error_response_srv_type = load_srv_type_with_fallback(
            UI_ERROR_RESPONSE_SRV_CLASS,
            LEGACY_CODE_COMMAND_SRV_CLASS
        )
        self.ui_error_notify_srv_type = load_srv_type_with_fallback(
            UI_ERROR_NOTIFY_SRV_CLASS,
            LEGACY_CODE_COMMAND_SRV_CLASS
        )
        self.book_detected_srv_type = load_srv_type(BOOK_DETECTED_SRV_CLASS)

        # ====================================================
        # UI -> Controller service clients
        # ====================================================
        self.cleanup_request_client = self.create_client(
            Empty,
            CLEANUP_REQUEST_SERVICE_NAME
        )

        self.error_response_client = None

        if self.ui_error_response_srv_type is not None:
            self.error_response_client = self.create_client(
                self.ui_error_response_srv_type,
                ERROR_RESPONSE_SERVICE_NAME
            )
        else:
            self.get_logger().error(
                f"{UI_ERROR_RESPONSE_SRV_CLASS} srv 타입을 찾지 못했습니다. "
                f"{CUSTOM_SRV_MODULE}.{UI_ERROR_RESPONSE_SRV_CLASS}가 필요합니다."
            )

        # ====================================================
        # Controller -> UI service servers
        # ====================================================
        if self.ui_error_notify_srv_type is not None:
            self.create_service(
                self.ui_error_notify_srv_type,
                UI_ERROR_NOTIFY_SERVICE_NAME,
                self.ui_error_notify_service_callback
            )
        else:
            self.get_logger().error(
                f"{UI_ERROR_NOTIFY_SERVICE_NAME} service server를 열 수 없습니다. "
                f"{CUSTOM_SRV_MODULE}.{UI_ERROR_NOTIFY_SRV_CLASS}가 필요합니다."
            )

        self.create_service(
            Trigger,
            UI_TASK_COMPLETE_SERVICE_NAME,
            self.ui_task_complete_service_callback
        )

        # 기존 QR 인식 테스트/DB 연동용 서비스는 유지한다.
        if self.book_detected_srv_type is not None:
            self.create_service(
                self.book_detected_srv_type,
                BOOK_DETECTED_SERVICE_NAME,
                self.book_detected_service_callback
            )
        else:
            self.get_logger().warning(
                "BookDetected srv 타입을 찾지 못했습니다. "
                "QR 인식 DB 조회 서비스만 비활성화합니다."
            )

        # ====================================================
        # Camera topic subscriber
        # ====================================================
        self.cv_bridge = None

        if IMAGE_STREAM_AVAILABLE:
            self.cv_bridge = CvBridge()
            self.create_subscription(
                Image,
                CAMERA_IMAGE_TOPIC_NAME,
                self.camera_image_callback,
                10
            )
        else:
            self.get_logger().warning(
                "sensor_msgs/cv_bridge를 불러오지 못해 카메라 스트림을 비활성화합니다."
            )

        self.get_logger().info(
            "book_binder_ui_node started / "
            f"clients: {CLEANUP_REQUEST_SERVICE_NAME}, {ERROR_RESPONSE_SERVICE_NAME} / "
            f"servers: {UI_ERROR_NOTIFY_SERVICE_NAME}, {UI_TASK_COMPLETE_SERVICE_NAME}"
        )

    # ========================================================
    # Public UI adapter
    # ========================================================
    def call_service(self, service_name, request_data=None, response_callback=None):
        """
        ui_1.py에서 호출하는 공통 요청 함수.

        ui_1.py는 ROS를 직접 모르고 아래 이름만 사용한다.
            cleanup_request 또는 sort_request
            error_response

        실제 ROS 서비스명은 이 파일에서 Controller 코드 기준으로 매핑한다.
        """
        if request_data is None:
            request_data = {}

        if service_name in ["cleanup_request", "sort_request", "start_classification"]:
            return self.call_cleanup_request(response_callback)

        if service_name == "error_response":
            return self.call_error_response(request_data, response_callback)

        if service_name == "emergency_stop":
            # 현재 Controller 코드에는 UI -> Controller 비상정지 전용 서비스가 없다.
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "message": "Controller에 emergency_stop 서비스가 정의되어 있지 않습니다."
                }
            )
            return False

        self.return_service_response(
            response_callback,
            {
                "result": SERVICE_REJECT,
                "success": False,
                "message": f"정의되지 않은 UI 요청입니다: {service_name}"
            }
        )
        return False

    # ========================================================
    # UI -> Controller clients
    # ========================================================
    def call_cleanup_request(self, response_callback=None):
        if not self.cleanup_request_client.wait_for_service(timeout_sec=0.2):
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "message": (
                        "cleanup_request 서비스 서버가 준비되지 않았습니다: "
                        f"{CLEANUP_REQUEST_SERVICE_NAME}"
                    )
                }
            )
            return False

        future = self.cleanup_request_client.call_async(Empty.Request())
        future.add_done_callback(
            lambda done_future: self.handle_generic_future(
                "cleanup_request",
                done_future,
                response_callback
            )
        )
        return True

    def call_error_response(self, request_data, response_callback=None):
        action_code = self.extract_code(request_data)

        if action_code not in [0, 1, 2]:
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "message": f"잘못된 오류대응 code입니다: {action_code}"
                }
            )
            return False

        return self.call_error_response_client(
            code=action_code,
            response_callback=response_callback
        )

    def call_error_response_client(self, code, response_callback=None):
        if self.ui_error_response_srv_type is None or self.error_response_client is None:
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "code": int(code),
                    "message": (
                        f"{UI_ERROR_RESPONSE_SRV_CLASS} srv 타입을 찾지 못했습니다. "
                        f"{CUSTOM_SRV_MODULE}.{UI_ERROR_RESPONSE_SRV_CLASS}가 필요합니다."
                    )
                }
            )
            return False

        if not self.error_response_client.wait_for_service(timeout_sec=0.2):
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "code": int(code),
                    "message": f"서비스 서버가 준비되지 않았습니다: {ERROR_RESPONSE_SERVICE_NAME}"
                }
            )
            return False

        request = self.ui_error_response_srv_type.Request()

        if not self.set_code_field(request, int(code)):
            self.return_service_response(
                response_callback,
                {
                    "result": SERVICE_REJECT,
                    "success": False,
                    "code": int(code),
                    "message": (
                        f"{UI_ERROR_RESPONSE_SRV_CLASS}.Request에서 code/action_code/response_code 계열 필드를 찾지 못했습니다."
                    )
                }
            )
            return False

        future = self.error_response_client.call_async(request)
        future.add_done_callback(
            lambda done_future: self.handle_generic_future(
                "error_response",
                done_future,
                response_callback,
                code=int(code)
            )
        )
        return True

    # ========================================================
    # Controller -> UI service servers
    # ========================================================
    def ui_error_notify_service_callback(self, request, response):
        """
        Controller -> UI 예외/오류 알림.

        request code 의미는 ui_1.py의 EXCEPTION_STOP_MSG와 동일하게 처리한다.
            0 엔트리포인트 이물질 감지
            1 로봇 안전정지상태 돌입
            2 테스크 진행 중 걸림/충돌/놓침
            3 비상정지 버튼 입력
            4 데이터 검색 불가
        """
        code = self.extract_code(request, default=None)

        if code is None:
            self.get_logger().warning("잘못된 ui_error_notify request 수신: code 필드 없음")
            self.set_success_response(response, False, "code 필드가 없습니다.")
            return response

        if code not in [0, 1, 2, 3, 4]:
            self.get_logger().warning(f"정의되지 않은 ui_error_notify code 수신: {code}")
            self.set_success_response(response, False, f"정의되지 않은 code: {code}")
            return response

        self.get_logger().warning(f"ui_error_notify service received: code={code}")
        self.exception_stop_signal.emit(code)

        self.set_success_response(response, True, "UI error notify accepted")
        return response

    def ui_task_complete_service_callback(self, request, response):
        """
        Controller -> UI 작업 완료 알림.
        Controller 코드가 /ui/task_complite 이름의 Trigger client를 사용하므로
        UI는 동일한 오타 이름으로 Trigger server를 연다.
        """
        self.get_logger().info("task_complite service received")
        self.clear_book_signal.emit()

        response.success = True
        response.message = "UI task complete accepted"
        return response

    def book_detected_service_callback(self, request, response):
        """
        기존 테스트/QR 인식 연동용 도서 인식 알림.
        request.qr_code 또는 request.book_id로 MongoDB를 조회한 뒤 UI에 표시한다.
        """
        qr_code = str(
            getattr(request, "qr_code", "")
            or getattr(request, "book_id", "")
            or getattr(request, "data", "")
            or ""
        ).strip()

        if not qr_code:
            self.get_logger().warning("빈 qr_code를 수신했습니다.")
            self.set_success_response(response, False, "빈 qr_code")
            return response

        book_doc = self.find_book_by_qr(qr_code)

        if book_doc is None:
            self.get_logger().warning(f"DB에서 도서 정보를 찾지 못했습니다: {qr_code}")

            # 데이터 검색 불가
            self.clear_book_signal.emit()
            self.exception_stop_signal.emit(4)

            self.set_success_response(response, False, "DB에서 도서 정보를 찾지 못했습니다.")
            return response

        self.book_info_signal.emit(book_doc)
        self.set_success_response(response, True, "book detected accepted")
        return response

    # ========================================================
    # Future/result helpers
    # ========================================================
    def handle_generic_future(
        self,
        service_name,
        future,
        response_callback=None,
        code=None
    ):
        try:
            response = future.result()
            success = self.extract_success(response, default=True)

            response_data = {
                "result": SERVICE_ACCEPT if success else SERVICE_REJECT,
                "success": success,
                "message": f"{service_name} 요청 전송 완료"
            }

            if code is not None:
                response_data["code"] = int(code)

        except Exception as e:
            response_data = {
                "result": SERVICE_REJECT,
                "success": False,
                "message": f"{service_name} 서비스 호출 실패: {e}"
            }

            if code is not None:
                response_data["code"] = int(code)

        self.return_service_response(response_callback, response_data)

    def return_service_response(self, response_callback, response_data):
        self.signal_bridge.service_response_signal.emit(
            response_callback,
            response_data
        )

    # ========================================================
    # DB lookup
    # ========================================================
    def find_book_by_qr(self, qr_code):
        if self.db_manager is None:
            self.get_logger().warning("DB manager가 연결되지 않았습니다.")
            return None

        method_names = [
            "find_book_by_qr",
            "find_book_by_qr_code",
            "get_book_by_qr",
            "get_book_by_qr_code",
            "find_book_by_id",
            "get_book_by_id",
        ]

        for method_name in method_names:
            method = getattr(self.db_manager, method_name, None)

            if method is None:
                continue

            try:
                result = method(qr_code)

                if result:
                    return self.normalize_book_doc(result)

            except Exception as e:
                self.get_logger().warning(
                    f"{method_name}({qr_code}) 조회 실패: {e}"
                )

        books = getattr(self.db_manager, "books", None)

        if books is None:
            return None

        query_candidates = [
            {"qr_code": qr_code},
            {"book_id": qr_code},
            {"qr_codes": qr_code},
            {"qr_codes": {"$in": [qr_code]}},
        ]

        for query in query_candidates:
            try:
                result = books.find_one(query)

                if result:
                    return self.normalize_book_doc(result)

            except Exception as e:
                self.get_logger().warning(
                    f"MongoDB 조회 실패 query={query}: {e}"
                )

        return None

    def normalize_book_doc(self, book_doc):
        if not isinstance(book_doc, dict):
            return book_doc

        doc = dict(book_doc)

        if "_id" in doc:
            doc["_id"] = str(doc["_id"])

        if "qr_code" not in doc and "book_id" in doc:
            doc["qr_code"] = doc["book_id"]

        return doc

    # ========================================================
    # Common helpers
    # ========================================================
    def extract_code(self, request_data, default=None):
        if isinstance(request_data, dict):
            for key in [
                "code", "action_code", "response_code", "error_action",
                "ui_action", "ui_response", "event_code", "exception_code",
                "status_code", "error_code"
            ]:
                value = request_data.get(key)

                if value not in [None, ""]:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return default

            return default

        for key in [
            "code", "action_code", "response_code", "error_action",
            "ui_action", "ui_response", "event_code", "exception_code",
            "status_code", "error_code"
        ]:
            if hasattr(request_data, key):
                value = getattr(request_data, key)

                if value not in [None, ""]:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return default

        # ROS2 generated request object의 필드 목록에서 정수형 필드를 fallback으로 찾는다.
        try:
            fields = request_data.get_fields_and_field_types()

            for field_name, field_type in fields.items():
                if "int" not in str(field_type).lower():
                    continue

                value = getattr(request_data, field_name, None)

                if value not in [None, ""]:
                    return int(value)

        except Exception:
            pass

        try:
            return int(request_data)
        except (TypeError, ValueError):
            return default

    def set_code_field(self, request, code):
        # 우선 컨트롤러와 맞출 가능성이 높은 필드명을 사용한다.
        for field_name in [
            "code", "action_code", "response_code", "error_action",
            "ui_action", "ui_response"
        ]:
            if hasattr(request, field_name):
                setattr(request, field_name, int(code))
                return True

        # 필드명이 다를 경우, 첫 번째 정수형 필드에 code를 넣는다.
        try:
            fields = request.get_fields_and_field_types()

            for field_name, field_type in fields.items():
                field_type_text = str(field_type).lower()

                if "int" in field_type_text:
                    setattr(request, field_name, int(code))
                    return True

                if "string" in field_type_text:
                    setattr(request, field_name, str(code))
                    return True

        except Exception:
            pass

        return False

    def extract_success(self, response, default=True):
        for key in ["success", "accepted", "ok"]:
            if hasattr(response, key):
                return bool(getattr(response, key))

        for key in ["result", "response", "response_code", "service_result", "status"]:
            if hasattr(response, key):
                value = getattr(response, key)

                if isinstance(value, bool):
                    return value

                if isinstance(value, int):
                    return value == SERVICE_ACCEPT

                if isinstance(value, str):
                    return value.strip().lower() in [
                        "0", "ok", "accept", "accepted", "true", "success", "성공"
                    ]

        return bool(default)

    def set_success_response(self, response, success, message=""):
        success = bool(success)

        for field_name in ["success", "accepted", "ok"]:
            if hasattr(response, field_name):
                setattr(response, field_name, success)

        for field_name in ["result", "response", "response_code", "service_result", "status"]:
            if hasattr(response, field_name):
                try:
                    setattr(response, field_name, SERVICE_ACCEPT if success else SERVICE_REJECT)
                    break
                except Exception:
                    pass

        if message and hasattr(response, "message"):
            response.message = str(message)

        return response

    # ========================================================
    # Camera topic
    # ========================================================
    def camera_image_callback(self, msg):
        if self.cv_bridge is None:
            return

        try:
            frame = self.cv_bridge.imgmsg_to_cv2(
                msg,
                desired_encoding="bgr8"
            )
            self.camera_frame_signal.emit(frame)

        except Exception as e:
            self.get_logger().error(f"camera image convert failed: {e}")


def load_db_manager():
    try:
        from app.db.db_manager import BookDatabaseManager
        return BookDatabaseManager()

    except Exception:
        try:
            from db_manager import BookDatabaseManager
            return BookDatabaseManager()

        except Exception as e:
            print(f"DB manager load failed: {e}")
            return None


def main(args=None):
    rclpy.init(args=args)

    db_manager = load_db_manager()
    ui_node = UINode(db_manager=db_manager)

    app, main_win = create_ui(
        ui_node=ui_node,
        db_manager=db_manager
    )

    spin_thread = threading.Thread(
        target=rclpy.spin,
        args=(ui_node,),
        daemon=True
    )
    spin_thread.start()

    exit_code = 0

    try:
        exit_code = app.exec()

    finally:
        if rclpy.ok():
            rclpy.shutdown()

        spin_thread.join(timeout=1.0)

        if ui_node is not None:
            try:
                ui_node.destroy_node()
            except Exception:
                pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

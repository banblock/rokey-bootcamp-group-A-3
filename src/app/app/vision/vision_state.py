class VisionState:
    """
    역할:
    - QR 스캔 가능 여부, 위험 감지 여부, 로봇 작업 여부,
      이물질 감시 활성화 여부를 관리한다.
    - 상태 전환 로직을 한 곳에 모아 메인 노드를 단순하게 만든다.
    """

    def __init__(self):
        self.scan_enabled = True
        self.danger_detected = False
        self.robot_working = False
        self.intrusion_monitor_enabled = False

    def set_qr_confirmed(self):
        """QR 확정 후 QR 인식은 멈추고 로봇 작업/이물질 감지를 활성화한다."""
        self.scan_enabled = False
        self.robot_working = True
        self.intrusion_monitor_enabled = True

    def reset_scan(self):
        """다음 QR 인식을 시작할 수 있도록 상태를 초기화한다."""
        self.scan_enabled = True
        self.robot_working = False
        self.intrusion_monitor_enabled = False

    def set_danger(self, detected):
        """위험 감지 상태를 설정한다. 위험 상태에서는 QR 스캔을 멈춘다."""
        self.danger_detected = detected
        if detected:
            self.scan_enabled = False

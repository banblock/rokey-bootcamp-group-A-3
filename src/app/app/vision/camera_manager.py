import cv2


class CameraManager:
    """
    역할:
    - 웹캠을 열고 해상도/FPS/코덱을 설정한다.
    - 프레임을 읽어 메인 비전 노드에 제공한다.
    - 프로그램 종료 시 카메라 자원을 해제한다.
    """

    def __init__(
        self,
        camera_index=2,
        width=1280,
        height=720,
        fps=30,
        use_v4l2=True,
        use_mjpg=True,
    ):
        if use_v4l2:
            self.camera = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
        else:
            self.camera = cv2.VideoCapture(camera_index)

        if use_mjpg:
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.camera.set(cv2.CAP_PROP_FPS, fps)

        self.actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.actual_fps = self.camera.get(cv2.CAP_PROP_FPS)

        print(
            f"카메라 설정: {self.actual_width}x{self.actual_height}, "
            f"FPS={self.actual_fps:.1f}"
        )

    def is_opened(self):
        """카메라가 정상적으로 열렸는지 반환한다."""
        return self.camera.isOpened()

    def read(self):
        """카메라에서 프레임을 1장 읽어온다."""
        return self.camera.read()

    def close(self):
        """카메라 자원을 해제한다."""
        if self.camera.isOpened():
            self.camera.release()

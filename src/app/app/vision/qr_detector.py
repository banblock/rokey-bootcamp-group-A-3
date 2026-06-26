import cv2
import numpy as np


class QRDetector:
    """
    역할:
    - QR ROI 안에서 QR 코드를 검출하고 디코딩한다.
    - 1배, 2배, 3배 확대 영상과 CLAHE 대비 향상 영상을 검사한다.
    - 화면 표시나 상태 전환은 하지 않고, 검출 결과만 메인 노드에 반환한다.
    """

    def __init__(self, qr_roi=(600, 150, 450, 400)):
        self.detector = cv2.QRCodeDetector()
        self.qr_roi = qr_roi

    def set_roi(self, qr_roi):
        """QR 탐색 ROI를 변경한다."""
        self.qr_roi = qr_roi

    def get_region(self, frame):
        """QR ROI가 설정되어 있으면 해당 영역만 잘라 반환한다."""
        frame_h, frame_w = frame.shape[:2]

        if self.qr_roi is None:
            return {
                "ok": True,
                "region": frame,
                "offset_x": 0,
                "offset_y": 0,
                "error": None,
            }

        rx, ry, rw, rh = self.qr_roi

        if rx < 0 or ry < 0 or rx + rw > frame_w or ry + rh > frame_h:
            return {
                "ok": False,
                "region": None,
                "offset_x": 0,
                "offset_y": 0,
                "error": (
                    f"QR ROI가 화면 범위를 벗어났습니다. "
                    f"frame=({frame_w}, {frame_h}), qr_roi={self.qr_roi}"
                ),
            }

        region = frame[ry:ry + rh, rx:rx + rw]

        if region.size == 0:
            return {
                "ok": False,
                "region": None,
                "offset_x": rx,
                "offset_y": ry,
                "error": "QR ROI가 비어 있습니다.",
            }

        return {
            "ok": True,
            "region": region,
            "offset_x": rx,
            "offset_y": ry,
            "error": None,
        }

    def detect(self, frame):
        """
        QR을 검출/디코딩한다.

        반환 dict:
        - status:
            SUCCESS      : QR 검출 및 디코딩 성공
            DECODE_ERROR : QR 위치는 찾았지만 데이터 디코딩 실패
            NOT_FOUND    : QR 위치를 찾지 못함
            ROI_ERROR    : QR ROI가 잘못됨
        - data: QR 문자열. 실패 시 빈 문자열
        - points: 원본 프레임 좌표계의 QR 꼭짓점. 없으면 None
        - message: 상태 설명
        """
        region_info = self.get_region(frame)

        if not region_info["ok"]:
            return {
                "status": "ROI_ERROR",
                "data": "",
                "points": None,
                "message": region_info["error"],
            }

        region = region_info["region"]
        offset_x = region_info["offset_x"]
        offset_y = region_info["offset_y"]

        decoded_data = ""
        decoded_points = None
        detected_points = None

        for scale in (1.0, 2.0, 3.0):
            if scale == 1.0:
                resized = region
            else:
                resized = cv2.resize(
                    region,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC,
                )

            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            clahe = cv2.createCLAHE(
                clipLimit=2.0,
                tileGridSize=(8, 8),
            )
            enhanced = clahe.apply(gray)

            candidates = (resized, enhanced)

            for candidate in candidates:
                try:
                    qr_data, points, _ = self.detector.detectAndDecode(candidate)
                except cv2.error:
                    continue

                if points is None:
                    continue

                points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
                candidate_h, candidate_w = candidate.shape[:2]

                if (
                    points.shape[0] != 4
                    or not np.all(np.isfinite(points))
                    or np.any(points[:, 0] < 0)
                    or np.any(points[:, 1] < 0)
                    or np.any(points[:, 0] >= candidate_w)
                    or np.any(points[:, 1] >= candidate_h)
                ):
                    continue

                original_points = points / scale
                original_points[:, 0] += offset_x
                original_points[:, 1] += offset_y

                if detected_points is None:
                    detected_points = original_points.copy()

                if qr_data:
                    decoded_data = qr_data
                    decoded_points = original_points.copy()
                    break

            if decoded_data:
                break

        if detected_points is None and decoded_points is None:
            return {
                "status": "NOT_FOUND",
                "data": "",
                "points": None,
                "message": "QR 코드를 찾지 못했습니다.",
            }

        display_points = decoded_points if decoded_points is not None else detected_points
        display_points = np.asarray(display_points, dtype=np.int32)

        if not decoded_data:
            return {
                "status": "DECODE_ERROR",
                "data": "",
                "points": display_points,
                "message": "QR 위치는 검출했지만 데이터 디코딩에 실패했습니다.",
            }

        return {
            "status": "SUCCESS",
            "data": decoded_data,
            "points": display_points,
            "message": f"QR 인식 성공: {decoded_data}",
        }

import cv2
import numpy as np


class Visualizer:
    """
    역할:
    - ROI, QR 박스, 이물질 박스, 로봇팔 마커, 알람 메시지 등
      화면 표시와 관련된 함수만 모아둔다.
    - 인식 알고리즘과 화면 표시 코드를 분리해 메인 노드를 단순하게 만든다.
    """

    def __init__(self, on_frame=None):
        self.on_frame = on_frame

    @staticmethod
    def draw_qr_roi(frame, qr_roi):
        """QR 탐색 ROI를 노란색 박스로 표시한다."""
        if qr_roi is None:
            return

        rx, ry, rw, rh = qr_roi
        cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 255, 0), 2)
        cv2.putText(
            frame,
            "QR ROI",
            (rx, max(25, ry - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2,
        )

    @staticmethod
    def draw_roi(frame, roi):
        """이물질 감지 ROI를 노란색 박스로 표시한다."""
        x, y, w, h = roi
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 0), 2)
        cv2.putText(
            frame,
            "ROI",
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2,
        )

    @staticmethod
    def draw_intrusion_area(frame, bbox):
        """이물질 감지 대상 영역을 주황색 박스와 텍스트로 표시한다."""
        x, y, w, h = bbox
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 2)

        text_y = y + h + 25
        if text_y >= frame.shape[0]:
            text_y = y + h - 15

        cv2.putText(
            frame,
            "INTRUSION AREA",
            (x, max(25, text_y)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 165, 255),
            2,
        )

    @staticmethod
    def draw_qr_box(frame, points):
        """QR 꼭짓점 polygon과 bounding box를 화면에 표시한다."""
        if points is None:
            return

        points = points.astype(np.int32)
        cv2.polylines(frame, [points], True, (255, 0, 255), 2)

        x, y, w, h = cv2.boundingRect(points)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 255), 2)
        cv2.putText(
            frame,
            "QR",
            (x, max(25, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 0, 255),
            2,
        )

    @staticmethod
    def draw_intrusion_boxes(frame, bboxes):
        """감지된 이물질 후보 bbox들을 빨간색 박스로 표시한다."""
        for bbox in bboxes:
            x, y, w, h = bbox
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(
                frame,
                "INTRUSION",
                (x, max(25, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )

    @staticmethod
    def draw_robot_markers(frame, marker_centers, marker_bboxes):
        """로봇팔 스티커 bbox, 중심점, 연결선을 화면에 표시한다."""
        for bbox in marker_bboxes:
            x, y, w, h = bbox
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(
                frame,
                "ROBOT_MARKER",
                (x, max(25, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 0),
                2,
            )

        if len(marker_centers) >= 2:
            sorted_centers = Visualizer.sort_marker_centers(marker_centers)
            for i in range(len(sorted_centers) - 1):
                cv2.line(frame, sorted_centers[i], sorted_centers[i + 1], (255, 0, 0), 3)

        for center in marker_centers:
            cv2.circle(frame, center, 5, (255, 0, 0), -1)

    @staticmethod
    def show_alarm_message(frame, text):
        """화면 상단에 빨간색 알람 배너를 표시한다."""
        frame_h, frame_w = frame.shape[:2]
        cv2.rectangle(frame, (10, 10), (frame_w - 10, 70), (0, 0, 255), -1)
        cv2.putText(
            frame,
            text,
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

    @staticmethod
    def draw_text(frame, text, color, position=(20, 40)):
        """지정한 위치에 상태 텍스트를 표시한다."""
        cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    def show_frame(self, frame):
        """
        외부 UI 콜백이 있으면 프레임을 콜백으로 전달하고,
        없으면 cv2.imshow()로 직접 표시한다.
        """
        if self.on_frame is not None:
            self.on_frame(frame)
        else:
            cv2.imshow("Book Vision", frame)

    @staticmethod
    def sort_marker_centers(marker_centers):
        """마커 중심점들을 x축 또는 y축 기준으로 정렬한다."""
        if len(marker_centers) <= 1:
            return marker_centers

        xs = [p[0] for p in marker_centers]
        ys = [p[1] for p in marker_centers]

        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)

        if x_range >= y_range:
            return sorted(marker_centers, key=lambda p: p[0])

        return sorted(marker_centers, key=lambda p: p[1])

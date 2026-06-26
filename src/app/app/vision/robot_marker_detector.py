from collections import deque

import cv2
import numpy as np


class RobotMarkerDetector:
    """
    역할:
    - 로봇팔에 붙인 파란색 스티커를 검출한다.
    - 스티커 중심점을 연결해 로봇팔 영역 마스크를 만든다.
    - 현재/최근 로봇팔 마스크를 합쳐 이물질 감지에서 제외할 ignore mask를 만든다.
    - 로봇팔이 빠르게 움직이는지 판단해 motion 기반 오탐을 줄인다.
    """

    def __init__(
        self,
        marker_lower_hsv=None,
        marker_upper_hsv=None,
        marker_min_area=80,
        marker_max_area=5000,
        marker_bbox_padding=15,
        min_marker_count=2,
        arm_line_thickness=50,
        arm_mask_dilate_size=25,
        mask_history_size=5,
        use_mask_history=True,
        mask_missing_max=3,
        fast_motion_threshold=15,
        fast_motion_hold_frames=7,
    ):
        self.marker_lower_hsv = (
            np.array([90, 80, 80], dtype=np.uint8)
            if marker_lower_hsv is None
            else marker_lower_hsv
        )
        self.marker_upper_hsv = (
            np.array([130, 255, 255], dtype=np.uint8)
            if marker_upper_hsv is None
            else marker_upper_hsv
        )

        self.marker_min_area = marker_min_area
        self.marker_max_area = marker_max_area
        self.marker_bbox_padding = marker_bbox_padding
        self.min_marker_count = min_marker_count

        self.arm_line_thickness = arm_line_thickness
        self.arm_mask_dilate_size = arm_mask_dilate_size

        self.prev_arm_mask = None
        self.arm_mask_history = deque(maxlen=mask_history_size)
        self.use_mask_history = use_mask_history

        self.mask_missing_count = 0
        self.mask_missing_max = mask_missing_max

        self.prev_marker_centroid = None
        self.fast_motion_threshold = fast_motion_threshold
        self.fast_motion_hold_frames = fast_motion_hold_frames
        self.fast_motion_count = 0

        self.show_debug_masks = False

    def reset(self):
        """로봇팔 마스크, 마커 중심점, 빠른 이동 상태를 초기화한다."""
        self.prev_arm_mask = None
        self.arm_mask_history.clear()
        self.mask_missing_count = 0
        self.prev_marker_centroid = None
        self.fast_motion_count = 0

    def detect_stickers(self, frame):
        """
        파란색 HSV 범위로 로봇팔 스티커를 검출한다.

        반환:
        - marker_centers: 각 스티커 중심점 리스트
        - marker_bboxes: 각 스티커 bbox 리스트
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        mask = cv2.inRange(
            hsv,
            self.marker_lower_hsv,
            self.marker_upper_hsv,
        )

        kernel = np.ones((5, 5), np.uint8)

        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        if self.show_debug_masks:
            cv2.imshow("Robot Sticker Mask", mask)

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        marker_centers = []
        marker_bboxes = []

        frame_h, frame_w = frame.shape[:2]

        for cnt in contours:
            area = cv2.contourArea(cnt)

            if area < self.marker_min_area:
                continue

            if area > self.marker_max_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            if w <= 0 or h <= 0:
                continue

            cx = x + w // 2
            cy = y + h // 2

            pad = self.marker_bbox_padding

            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(frame_w, x + w + pad)
            y2 = min(frame_h, y + h + pad)

            marker_centers.append((cx, cy))
            marker_bboxes.append((x1, y1, x2 - x1, y2 - y1))

        return marker_centers, marker_bboxes

    def build_arm_mask(self, frame, marker_centers):
        """스티커 중심점들을 연결해 로봇팔 영역 마스크를 만든다."""
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)

        if len(marker_centers) < self.min_marker_count:
            return mask

        marker_centers = self.sort_marker_centers(marker_centers)

        for i in range(len(marker_centers) - 1):
            p1 = marker_centers[i]
            p2 = marker_centers[i + 1]
            cv2.line(mask, p1, p2, 255, self.arm_line_thickness)

        radius = self.arm_line_thickness // 2 + self.marker_bbox_padding

        for center in marker_centers:
            cv2.circle(mask, center, radius, 255, -1)

        if self.arm_mask_dilate_size > 0:
            expand_kernel = np.ones(
                (self.arm_mask_dilate_size, self.arm_mask_dilate_size),
                np.uint8,
            )
            mask = cv2.dilate(mask, expand_kernel, iterations=1)

        if self.show_debug_masks:
            cv2.imshow("Robot Arm Mask", mask)

        return mask

    def build_ignore_mask(self, current_arm_mask):
        """현재 로봇팔 마스크와 최근 로봇팔 마스크를 합쳐 ignore mask를 만든다."""
        masks = []

        if current_arm_mask is not None and cv2.countNonZero(current_arm_mask) > 0:
            masks.append(current_arm_mask)

        if self.use_mask_history:
            for old_mask in self.arm_mask_history:
                if old_mask is None:
                    continue

                if masks and old_mask.shape != masks[0].shape:
                    continue

                masks.append(old_mask)

        elif (
            self.prev_arm_mask is not None
            and current_arm_mask is not None
            and self.prev_arm_mask.shape == current_arm_mask.shape
        ):
            masks.append(self.prev_arm_mask)

        if not masks:
            return None

        ignore_mask = np.zeros_like(masks[0])

        for mask in masks:
            ignore_mask = cv2.bitwise_or(ignore_mask, mask)

        if self.show_debug_masks:
            cv2.imshow("Robot Ignore Mask History", ignore_mask)

        return ignore_mask

    def update_prev_arm_mask(self, current_arm_mask):
        """
        현재 로봇팔 마스크를 이전 마스크와 history에 저장한다.
        마커가 잠깐 안 잡힐 때는 최근 마스크를 잠시 유지한다.
        """
        if current_arm_mask is None or cv2.countNonZero(current_arm_mask) == 0:
            self.mask_missing_count += 1

            if self.mask_missing_count > self.mask_missing_max:
                self.prev_arm_mask = None
                self.arm_mask_history.clear()

            return

        self.mask_missing_count = 0
        self.prev_arm_mask = current_arm_mask.copy()

        if self.use_mask_history:
            self.arm_mask_history.append(current_arm_mask.copy())

    def update_motion_state(self, marker_centers):
        """마커 중심점 평균 위치 변화량으로 로봇팔 빠른 이동 여부를 판단한다."""
        if len(marker_centers) < self.min_marker_count:
            if self.fast_motion_count > 0:
                self.fast_motion_count -= 1
                return True

            return False

        centers = np.array(marker_centers, dtype=np.float32)
        centroid = np.mean(centers, axis=0)

        fast_moving = False

        if self.prev_marker_centroid is not None:
            dx = centroid[0] - self.prev_marker_centroid[0]
            dy = centroid[1] - self.prev_marker_centroid[1]
            distance = np.sqrt(dx * dx + dy * dy)

            if distance >= self.fast_motion_threshold:
                self.fast_motion_count = self.fast_motion_hold_frames
                fast_moving = True

        self.prev_marker_centroid = centroid

        if self.fast_motion_count > 0:
            self.fast_motion_count -= 1
            fast_moving = True

        return fast_moving

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

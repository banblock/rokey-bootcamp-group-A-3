import cv2
import numpy as np


class IntrusionDetector:
    """
    역할:
    - QR 확정 후 로봇 작업 중, 감시 ROI 안에 손/이물질이 들어왔는지 감지한다.
    - 피부색 기반 감지와 움직임 기반 감지를 OR 조건으로 함께 사용한다.
    - 따라서 천천히 들어오는 손처럼 motion이 약한 경우도 skin mask로 감지할 수 있다.
    - 로봇팔 ignore mask 영역은 감지에서 제외한다.
    - 연속 프레임 조건으로 이물질 알람을 확정한다.

    주의:
    - 피부색과 비슷한 갈색/베이지색 상자나 테이프는 skin mask에 잡힐 수 있으므로,
      반납함 내부 재질은 피부색 계열을 피하는 것이 좋다.
    """

    def __init__(
        self,
        intrusion_ratio_threshold=0.06,
        min_intrusion_area=400,
        motion_threshold=35,
        confirm_frames=17,
    ):
        self.intrusion_ratio_threshold = intrusion_ratio_threshold
        self.min_intrusion_area = min_intrusion_area
        self.motion_threshold = motion_threshold

        # intrusion 후보가 이 프레임 수 이상 연속으로 유지되어야 alarm으로 확정한다.
        # 책 표지/그림 등에 의한 1~3프레임짜리 순간 오탐을 줄이기 위한 값이다.
        self.confirm_frames = confirm_frames

        self.prev_intrusion_gray = None
        self.intrusion_count = 0
        self.alarm = False
        self.show_debug_masks = False

    def reset(self):
        """이물질 감지용 이전 프레임, 카운터, 알람 상태를 초기화한다."""
        self.prev_intrusion_gray = None
        self.intrusion_count = 0
        self.alarm = False

    def detect(
        self,
        frame,
        monitor_bbox,
        use_motion=True,
        use_skin=True,
        ignore_mask=None,
    ):
        """
        monitor_bbox 내부의 이물질을 감지한다.

        핵심:
        - skin mask와 motion mask를 OR로 합쳐 intrusion 후보를 만든다.
        - 따라서 천천히 움직이는 손처럼 motion이 약한 물체도 피부색이면 감지할 수 있다.
        - 단, 실제 alarm은 update_alarm()에서 연속 confirm_frames 이상 유지될 때만 확정한다.

        반환 dict:
        - detected: 침범 후보가 있는지
        - bboxes: 침범 후보 bbox 리스트
        - pixel_ratio: 마스크 픽셀 기준 침범 비율
        - bbox_ratio: bbox 면적 기준 침범 비율
        """
        x, y, w, h = monitor_bbox
        monitor_roi = frame[y:y + h, x:x + w]

        if monitor_roi.size == 0:
            return self._empty_result()

        ignore_roi = None

        if ignore_mask is not None and cv2.countNonZero(ignore_mask) > 0:
            candidate_ignore_roi = ignore_mask[y:y + h, x:x + w]
            if candidate_ignore_roi.shape[:2] == monitor_roi.shape[:2]:
                ignore_roi = candidate_ignore_roi

        masks = []
        skin_mask = None
        motion_mask = None

        # ==========================================================
        # 1. 피부색 기반 손/이물질 감지
        # ==========================================================
        if use_skin:
            ycrcb = cv2.cvtColor(monitor_roi, cv2.COLOR_BGR2YCrCb)
            lower_skin = np.array([0, 133, 77], dtype=np.uint8)
            upper_skin = np.array([255, 173, 127], dtype=np.uint8)

            skin_mask = cv2.inRange(ycrcb, lower_skin, upper_skin)

            if ignore_roi is not None:
                skin_mask = cv2.bitwise_and(
                    skin_mask,
                    cv2.bitwise_not(ignore_roi),
                )

            masks.append(skin_mask)

        # ==========================================================
        # 2. 움직임 기반 침범 감지
        # ==========================================================
        gray = cv2.cvtColor(monitor_roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if use_motion:
            if self.prev_intrusion_gray is None:
                # 첫 프레임은 비교 대상이 없으므로 기준 프레임만 저장한다.
                self.prev_intrusion_gray = gray.copy()

            elif self.prev_intrusion_gray.shape != gray.shape:
                self.prev_intrusion_gray = gray.copy()

            else:
                current_for_diff = gray.copy()
                prev_for_diff = self.prev_intrusion_gray.copy()

                if ignore_roi is not None:
                    current_for_diff[ignore_roi > 0] = 0
                    prev_for_diff[ignore_roi > 0] = 0

                diff = cv2.absdiff(prev_for_diff, current_for_diff)
                self.prev_intrusion_gray = gray.copy()

                _, motion_mask = cv2.threshold(
                    diff,
                    self.motion_threshold,
                    255,
                    cv2.THRESH_BINARY,
                )

                if ignore_roi is not None:
                    motion_mask = cv2.bitwise_and(
                        motion_mask,
                        cv2.bitwise_not(ignore_roi),
                    )

                masks.append(motion_mask)

        else:
            # 로봇팔이 빠르게 움직이는 동안 motion 감지는 끌 수 있지만,
            # 기준 프레임은 계속 현재 프레임으로 갱신한다.
            # skin 감지는 별도로 use_skin=True이면 계속 사용할 수 있다.
            self.prev_intrusion_gray = gray.copy()

        if not masks:
            self._show_debug_masks(skin_mask, motion_mask, None)
            return self._empty_result()

        # ==========================================================
        # 3. 최종 mask 생성: skin OR motion
        # ==========================================================
        combined_mask = masks[0]
        for mask in masks[1:]:
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        kernel = np.ones((5, 5), np.uint8)
        combined_mask = cv2.morphologyEx(
            combined_mask,
            cv2.MORPH_OPEN,
            kernel,
            iterations=1,
        )
        combined_mask = cv2.morphologyEx(
            combined_mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=2,
        )

        if ignore_roi is not None:
            combined_mask = cv2.bitwise_and(
                combined_mask,
                cv2.bitwise_not(ignore_roi),
            )
            combined_mask = cv2.morphologyEx(
                combined_mask,
                cv2.MORPH_OPEN,
                kernel,
                iterations=1,
            )

        self._show_debug_masks(skin_mask, motion_mask, combined_mask)

        intrusion_pixels = cv2.countNonZero(combined_mask)
        monitor_area = w * h
        pixel_ratio = intrusion_pixels / monitor_area if monitor_area > 0 else 0.0

        contours, _ = cv2.findContours(
            combined_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        intrusion_bboxes = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_intrusion_area:
                continue

            ix, iy, iw, ih = cv2.boundingRect(cnt)
            if iw <= 0 or ih <= 0:
                continue

            intrusion_bboxes.append((ix + x, iy + y, iw, ih))

        bbox_ratio = self.calculate_bbox_ratio(intrusion_bboxes, monitor_bbox)
        detected = (
            bbox_ratio >= self.intrusion_ratio_threshold
            and len(intrusion_bboxes) > 0
        )

        return {
            "detected": detected,
            "bboxes": intrusion_bboxes,
            "pixel_ratio": pixel_ratio,
            "bbox_ratio": bbox_ratio,
        }

    @staticmethod
    def _empty_result():
        """감지 결과가 없을 때 반환할 기본 dict를 만든다."""
        return {
            "detected": False,
            "bboxes": [],
            "pixel_ratio": 0.0,
            "bbox_ratio": 0.0,
        }

    def _show_debug_masks(self, skin_mask, motion_mask, combined_mask):
        """디버그 모드에서 skin/motion/최종 mask를 표시한다."""
        if not self.show_debug_masks:
            return

        if skin_mask is not None:
            cv2.imshow("Intrusion Skin Mask", skin_mask)

        if motion_mask is not None:
            cv2.imshow("Intrusion Motion Mask", motion_mask)

        if combined_mask is not None:
            cv2.imshow("Area Intrusion Mask After Robot Ignore", combined_mask)

    @staticmethod
    def calculate_bbox_ratio(intrusion_bboxes, monitor_bbox):
        """감지된 이물질 bbox들의 총 면적이 감시 ROI에서 차지하는 비율을 계산한다."""
        if not intrusion_bboxes or monitor_bbox is None:
            return 0.0

        _, _, monitor_w, monitor_h = monitor_bbox
        monitor_area = monitor_w * monitor_h

        if monitor_area <= 0:
            return 0.0

        total_area = 0

        for bbox in intrusion_bboxes:
            _, _, w, h = bbox
            if w <= 0 or h <= 0:
                continue
            total_area += w * h

        return total_area / monitor_area

    def update_alarm(self, detected):
        """
        이물질 감지가 연속으로 confirm_frames 이상 유지되는지 확인한다.

        반환 dict:
        - alarm: 알람 확정 여부
        - count: 현재 연속 감지 프레임 수
        - cleared: 기존 알람이 해제되었는지
        """
        cleared = False

        if detected:
            self.intrusion_count += 1
            if self.intrusion_count >= self.confirm_frames:
                self.alarm = True
            return {
                "alarm": self.alarm,
                "count": self.intrusion_count,
                "cleared": False,
            }

        if self.alarm:
            cleared = True

        self.intrusion_count = 0
        self.alarm = False
        return {
            "alarm": False,
            "count": 0,
            "cleared": cleared,
        }

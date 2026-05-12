# tests/test_detect_regions.py
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VALID_CLASSES = {
    "sender_block", "receiver_block", "tracking_number",
    "address_block", "content_block", "fee_block", "datetime_block",
}


def _make_mock_yolo_result(cls_id: int, cls_name: str, bbox: list, conf: float):
    mock_box = MagicMock()
    mock_box.cls.item.return_value = cls_id
    mock_box.conf.item.return_value = conf
    mock_box.xyxy.__getitem__ = MagicMock(return_value=MagicMock())
    mock_box.xyxy[0].tolist.return_value = bbox
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.names = {cls_id: cls_name}
    return mock_result


def test_detect_regions_returns_dict_of_known_classes():
    mock_result = _make_mock_yolo_result(0, "sender_block", [10, 10, 200, 100], 0.95)

    with patch("ultralytics.YOLO") as MockYOLO:
        MockYOLO.return_value.return_value = [mock_result]
        from src.detect_regions import detect_regions
        img = np.zeros((800, 600, 3), dtype=np.uint8)
        regions = detect_regions(img, model_path="fake_model.pt")

    assert isinstance(regions, dict)
    assert "sender_block" in regions
    for cls_name in regions:
        assert cls_name in VALID_CLASSES


def test_detect_regions_box_is_5_tuple():
    mock_result = _make_mock_yolo_result(1, "receiver_block", [50, 50, 300, 200], 0.88)

    with patch("ultralytics.YOLO") as MockYOLO:
        MockYOLO.return_value.return_value = [mock_result]
        from src.detect_regions import detect_regions
        img = np.zeros((800, 600, 3), dtype=np.uint8)
        regions = detect_regions(img, model_path="fake_model.pt")

    boxes = regions["receiver_block"]
    assert len(boxes) == 1
    x1, y1, x2, y2, conf = boxes[0]
    assert x1 == 50 and y1 == 50 and x2 == 300 and y2 == 200
    assert abs(conf - 0.88) < 0.01


def test_detect_regions_empty_when_no_detection():
    mock_result = MagicMock()
    mock_result.boxes = []
    mock_result.names = {}

    with patch("ultralytics.YOLO") as MockYOLO:
        MockYOLO.return_value.return_value = [mock_result]
        from src.detect_regions import detect_regions
        img = np.zeros((800, 600, 3), dtype=np.uint8)
        regions = detect_regions(img, model_path="fake_model.pt")

    assert regions == {}


def test_detect_regions_multiple_boxes_same_class():
    mock_box1 = MagicMock()
    mock_box1.cls.item.return_value = 1
    mock_box1.conf.item.return_value = 0.9
    mock_box1.xyxy.__getitem__ = MagicMock(return_value=MagicMock())
    mock_box1.xyxy[0].tolist.return_value = [10, 10, 100, 50]

    mock_box2 = MagicMock()
    mock_box2.cls.item.return_value = 1
    mock_box2.conf.item.return_value = 0.7
    mock_box2.xyxy.__getitem__ = MagicMock(return_value=MagicMock())
    mock_box2.xyxy[0].tolist.return_value = [10, 60, 100, 110]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box1, mock_box2]
    mock_result.names = {1: "receiver_block"}

    with patch("ultralytics.YOLO") as MockYOLO:
        MockYOLO.return_value.return_value = [mock_result]
        from src.detect_regions import detect_regions
        img = np.zeros((800, 600, 3), dtype=np.uint8)
        regions = detect_regions(img, model_path="fake_model.pt")

    assert len(regions["receiver_block"]) == 2


def test_detect_regions_sender_block_keeps_single_box():
    # A tighter left box with slightly lower conf should beat an oversized right box.
    mock_box_left = MagicMock()
    mock_box_left.cls.item.return_value = 0
    mock_box_left.conf.item.return_value = 0.59
    mock_box_left.xyxy.__getitem__ = MagicMock(return_value=MagicMock())
    mock_box_left.xyxy[0].tolist.return_value = [40, 60, 380, 620]

    mock_box_big_right = MagicMock()
    mock_box_big_right.cls.item.return_value = 0
    mock_box_big_right.conf.item.return_value = 0.66
    mock_box_big_right.xyxy.__getitem__ = MagicMock(return_value=MagicMock())
    mock_box_big_right.xyxy[0].tolist.return_value = [300, 20, 1180, 760]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box_left, mock_box_big_right]
    mock_result.names = {0: "sender_block"}

    with patch("ultralytics.YOLO") as MockYOLO:
        MockYOLO.return_value.return_value = [mock_result]
        from src.detect_regions import detect_regions
        img = np.zeros((800, 1200, 3), dtype=np.uint8)
        regions = detect_regions(img, model_path="fake_model.pt")

    assert len(regions["sender_block"]) == 1
    x1, y1, x2, y2, conf = regions["sender_block"][0]
    assert (x1, y1, x2, y2) == (40, 60, 380, 620)
    assert abs(conf - 0.59) < 0.01
